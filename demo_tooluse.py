"""
APPROCCIO 2: Tool Use nativo (Groq, formato OpenAI)
====================================================
Definiamo le funzioni nel codice e le descriviamo al modello
tramite il campo "tools" nella richiesta.
Il modello non scrive tag: risponde con un oggetto JSON strutturato
che indica quale funzione chiamare e con quali argomenti.

Il loop è bidirezionale:
  1. Utente → modello
  2. Modello → tool_call (JSON strutturato, non testo libero)
  3. Codice esegue la funzione Python
  4. Risultato → modello (ruolo "tool")
  5. Modello → risposta finale in linguaggio naturale
"""

import os
import json
from groq import Groq

# ─── Colori ANSI ─────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
BLUE    = "\033[94m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
RED     = "\033[91m"
MAGENTA = "\033[95m"

MODEL = "llama-3.3-70b-versatile"
_COLORE_RUOLO = {"system": RESET, "user": BLUE, "assistant": GREEN, "tool": MAGENTA}

def stampa_conversazione(history: list):
    """Stampa tutta la conversazione come JSON. Ogni messaggio è colorato per ruolo."""
    print(f"\n{YELLOW}── CONVERSAZIONE ────────────────────────────")
    print(f'{{"model": "{MODEL}", "messages": [')
    for i, msg in enumerate(history):
        colore = _COLORE_RUOLO.get(msg.get("role", ""), RESET)
        sep = "," if i < len(history) - 1 else ""
        print(f"  {colore}{json.dumps(msg, ensure_ascii=False)}{sep}{RESET}")
    print(f"]}}")
    print(f"─────────────────────────────────────────────{RESET}\n")

# ─── Stato casse (locale, in memoria) ─────────────────────────────────────────
casse = [False, False, False, False]

def mostra_stato():
    print(f"\n{CYAN}╔══════════════════════════════╗")
    for i, aperta in enumerate(casse):
        if aperta:
            print(f"║  CASSA {i}: 🟢 APERTA         ║")
        else:
            print(f"║  CASSA {i}: 🔴 CHIUSA         ║")
    print(f"╚══════════════════════════════╝{RESET}\n")

# ─── Funzioni reali che gestiscono le casse ───────────────────────────────────

def apri_cassa(numero: int) -> str:
    if not 0 <= numero <= 3:
        return f"Errore: cassa {numero} non esiste. Le casse valide sono 0, 1, 2, 3."
    casse[numero] = True
    return f"Cassa {numero} aperta con successo."

def chiudi_cassa(numero: int) -> str:
    if not 0 <= numero <= 3:
        return f"Errore: cassa {numero} non esiste. Le casse valide sono 0, 1, 2, 3."
    casse[numero] = False
    return f"Cassa {numero} chiusa con successo."

def stato_cassa(numero: int) -> str:
    if not 0 <= numero <= 3:
        return f"Errore: cassa {numero} non esiste."
    stato = "aperta" if casse[numero] else "chiusa"
    return f"Cassa {numero} è attualmente {stato}."

FUNZIONI_DISPONIBILI = {
    "apri_cassa": apri_cassa,
    "chiudi_cassa": chiudi_cassa,
    "stato_cassa": stato_cassa,
}

"""
In metito ai formati di uso dei tool, openai è lo stesso di antropic grok?

No - sia nel json dei messaggi, l'uso dei tool differisce, sia che con le tool_definitions

Json uso tool:

  Groq / OpenAI
  {"role": "tool", "tool_call_id": "abc123", "content": "Cassa 2 aperta."}                           
  I risultati dei tool vanno come messaggi con role: "tool" e si riferiscono alla call tramite       
  tool_call_id.                                                                                      

  Anthropic (Claude):                                                                                
  {"role": "user", "content": [                                                                      
    {"type": "tool_result", "tool_use_id": "abc123", "content": "Cassa 2 aperta."}

  I risultati dei tool vanno dentro un messaggio role: "user" come array di blocchi tipizzati. Anche 
  le tool call del modello hanno un formato diverso (type: "tool_use" invece di function).

  Gemini è ancora diverso — usa oggetti Python typed (FunctionResponse, FunctionCall) invece di JSON 
  puro, come vedi in demo_mcp.py nella versione originale con Gemini.
"""

# ─── Definizione dei tool (formato OpenAI, usato anche da Groq) ───────────────
# Queste definizioni vengono mandate al modello ad ogni chiamata.
# Il modello le usa per decidere quando e come invocare le funzioni.
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "apri_cassa",
            "description": "Apre una cassa del supermercato rendendola operativa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "numero": {
                        "type": "integer",
                        "description": "Il numero della cassa da aprire (0, 1, 2 o 3)",
                    }
                },
                "required": ["numero"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chiudi_cassa",
            "description": "Chiude una cassa del supermercato.",
            "parameters": {
                "type": "object",
                "properties": {
                    "numero": {
                        "type": "integer",
                        "description": "Il numero della cassa da chiudere (0, 1, 2 o 3)",
                    }
                },
                "required": ["numero"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stato_cassa",
            "description": "Controlla se una cassa è aperta o chiusa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "numero": {
                        "type": "integer",
                        "description": "Il numero della cassa di cui controllare lo stato (0, 1, 2 o 3)",
                    }
                },
                "required": ["numero"],
            },
        },
    },
]

SYSTEM_PROMPT = """Sei un assistente per la gestione delle casse di un supermercato.
Hai a disposizione 4 casse, numerate da 0 a 3.
Usa i tool disponibili per aprire, chiudere o controllare lo stato delle casse.
Se l'utente chiede di agire su più casse (es. "tutte" o "le pari"), chiama il tool più volte.
Rispondi sempre in italiano, in modo conciso."""

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print(f"{RED}Errore: variabile d'ambiente GROQ_API_KEY non impostata.{RESET}")
        return

    client = Groq(api_key=api_key)

    print(f"\n{BOLD}{'='*50}")
    print("  DEMO 2: Tool Use Nativo  [Groq]")
    print(f"{'='*50}{RESET}")
    print("Scrivi comandi in italiano per gestire le casse.\n")

    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    mostra_stato()

    while True:
        try:
            utente = input(f"{BLUE}Tu: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nUscita.")
            break

        if not utente:
            continue
        if utente.lower() in ("exit", "quit", "esci"):
            break

        history.append({"role": "user", "content": utente})

        risposta = client.chat.completions.create(
            model=MODEL,
            messages=history,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto", #se rispondere o usare i tool
        )

        # ── Loop: il modello può fare più tool call prima della risposta finale ─
        while True:
            msg = risposta.choices[0].message
            finish_reason = risposta.choices[0].finish_reason #stop se si è conclusa, length se ha raggiunto il massimo di lunghezza per risposta, content_filter per censura, tool_calls se usa un tool - e non scrive testo

            # Costruiamo il dict del messaggio e lo aggiungiamo subito alla storia
            msg_dict = {"role": "assistant"}
            if msg.content:
                msg_dict["content"] = msg.content
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ]
            history.append(msg_dict)

            # Stampiamo tutta la conversazione (risposta del modello già inclusa)
            stampa_conversazione(history)

            if finish_reason != "tool_calls" or not msg.tool_calls:
                # Risposta testuale finale
                print(f"{GREEN}Modello: {msg.content}{RESET}\n")
                break

            # ── Il modello ha chiesto di eseguire uno o più tool ───────────────
            for tc in msg.tool_calls:
                nome = tc.function.name
                args = json.loads(tc.function.arguments)

                print(f"{MAGENTA}[TOOL CALL] {nome}({args}){RESET}")

                risultato = FUNZIONI_DISPONIBILI[nome](**args) if nome in FUNZIONI_DISPONIBILI \
                    else f"Errore: funzione {nome} non trovata."

                print(f"{MAGENTA}[TOOL RESULT] {risultato}{RESET}")

                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": risultato,
                })

            # Nuova chiamata al modello con i risultati dei tool
            risposta = client.chat.completions.create(
                model=MODEL,
                messages=history,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )

        mostra_stato()

if __name__ == "__main__":
    main()
