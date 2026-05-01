"""
APPROCCIO 2: Tool Use nativo delle API Gemini
==============================================
Definiamo le funzioni direttamente nel codice e le descriviamo al modello
tramite function_declarations. Il modello non scrive tag: chiede esplicitamente
di eseguire una funzione con parametri strutturati (JSON).

Il loop è bidirezionale:
  1. Utente → modello
  2. Modello → richiesta di tool call (non risposta testuale)
  3. Codice esegue la funzione
  4. Risultato → modello
  5. Modello → risposta finale in linguaggio naturale
"""

import os
import json
import google.genai as genai
import google.genai.types as types
from gemini_retry import chiama_con_retry

# ─── Colori ANSI ─────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
BLUE    = "\033[94m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
RED     = "\033[91m"
MAGENTA = "\033[95m"

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
# Queste sono le funzioni Python che il modello può "chiamare".
# Restituiscono una stringa che viene rimandato al modello come feedback.

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

# Mappa nome_funzione → funzione Python (usata quando arriva la tool call)
FUNZIONI_DISPONIBILI = {
    "apri_cassa": apri_cassa,
    "chiudi_cassa": chiudi_cassa,
    "stato_cassa": stato_cassa,
}

# ─── Definizione dei tool per il modello ──────────────────────────────────────
# Qui descriviamo al modello cosa può fare. Il modello userà queste descrizioni
# per decidere quando e come chiamare le funzioni.
TOOL_DEFINITIONS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="apri_cassa",
            description="Apre una cassa del supermercato rendendola operativa.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "numero": types.Schema(
                        type=types.Type.INTEGER,
                        description="Il numero della cassa da aprire (0, 1, 2 o 3)",
                    )
                },
                required=["numero"],
            ),
        ),
        types.FunctionDeclaration(
            name="chiudi_cassa",
            description="Chiude una cassa del supermercato.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "numero": types.Schema(
                        type=types.Type.INTEGER,
                        description="Il numero della cassa da chiudere (0, 1, 2 o 3)",
                    )
                },
                required=["numero"],
            ),
        ),
        types.FunctionDeclaration(
            name="stato_cassa",
            description="Controlla se una cassa è aperta o chiusa.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "numero": types.Schema(
                        type=types.Type.INTEGER,
                        description="Il numero della cassa di cui controllare lo stato (0, 1, 2 o 3)",
                    )
                },
                required=["numero"],
            ),
        ),
    ]
)

SYSTEM_PROMPT = """Sei un assistente per la gestione delle casse di un supermercato.
Hai a disposizione 4 casse, numerate da 0 a 3.
Usa i tool disponibili per aprire, chiudere o controllare lo stato delle casse.
Se l'utente chiede di agire su più casse (es. "tutte" o "le pari"), chiama il tool più volte.
Rispondi sempre in italiano, in modo conciso."""

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(f"{RED}Errore: variabile d'ambiente GEMINI_API_KEY non impostata.{RESET}")
        return

    client = genai.Client(api_key=api_key)

    print(f"\n{BOLD}{'='*50}")
    print("  DEMO 2: Tool Use Nativo Gemini")
    print(f"{'='*50}{RESET}")
    print("Scrivi comandi in italiano per gestire le casse.\n")

    history = []
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

        history.append(types.Content(role="user", parts=[types.Part(text=utente)]))

        # ── Primo turno: il modello potrebbe rispondere con tool call ─────────
        print(f"\n{YELLOW}── REQUEST (turno 1) ────────────────────────")
        print(json.dumps({"contents": [{"role": c.role, "parts": [str(p) for p in c.parts]} for c in history]}, ensure_ascii=False, indent=2))
        print(f"─────────────────────────────────────────────{RESET}\n")

        risposta = chiama_con_retry(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[TOOL_DEFINITIONS],
            ),
        )

        # ── Elaboriamo la risposta: può contenere tool calls o testo finale ───
        # Il modello può chiedere di eseguire più tool nella stessa risposta
        while True:
            candidate = risposta.candidates[0]
            parts_risposta = candidate.content.parts

            # Mostriamo la risposta grezza
            parts_debug = []
            for p in parts_risposta:
                if p.text:
                    parts_debug.append({"text": p.text})
                elif p.function_call:
                    parts_debug.append({
                        "function_call": {
                            "name": p.function_call.name,
                            "args": dict(p.function_call.args)
                        }
                    })
            print(f"{YELLOW}── RESPONSE ─────────────────────────────────")
            print(json.dumps({"parts": parts_debug, "finish_reason": str(candidate.finish_reason)}, ensure_ascii=False, indent=2))
            print(f"─────────────────────────────────────────────{RESET}\n")

            # Controlliamo se ci sono tool calls in questa risposta
            tool_calls = [p for p in parts_risposta if p.function_call]

            if not tool_calls:
                # Nessun tool call: il modello ha generato la risposta testuale finale
                testo_finale = "".join(p.text for p in parts_risposta if p.text)
                print(f"{GREEN}Modello: {testo_finale}{RESET}\n")
                history.append(candidate.content)
                break

            # ── Il modello ha chiesto di eseguire dei tool ─────────────────────
            # Aggiungiamo la risposta del modello (con le tool calls) alla storia
            history.append(candidate.content)

            # Eseguiamo ogni tool call e raccogliamo i risultati
            risultati_parts = []
            for part in tool_calls:
                fc = part.function_call
                nome_funzione = fc.name
                args = dict(fc.args)

                print(f"{MAGENTA}[TOOL CALL] {nome_funzione}({args}){RESET}")

                # Esecuzione reale della funzione Python
                if nome_funzione in FUNZIONI_DISPONIBILI:
                    risultato = FUNZIONI_DISPONIBILI[nome_funzione](**args)
                else:
                    risultato = f"Errore: funzione {nome_funzione} non trovata."

                print(f"{MAGENTA}[TOOL RESULT] {risultato}{RESET}")

                # Prepariamo il risultato da rimandare al modello
                risultati_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=nome_funzione,
                            response={"result": risultato},
                        )
                    )
                )

            # ── Rimandare i risultati al modello (il loop chiuso) ──────────────
            # Questo è il cuore della differenza rispetto all'approccio 1:
            # il modello riceve il feedback e può ragionare sul risultato
            history.append(types.Content(role="user", parts=risultati_parts))

            print(f"\n{YELLOW}── REQUEST (con risultati tool) ─────────────")
            print(json.dumps({"tool_results": [{"name": p.function_response.name, "response": p.function_response.response} for p in risultati_parts]}, ensure_ascii=False, indent=2))
            print(f"─────────────────────────────────────────────{RESET}\n")

            # Nuova chiamata al modello con i risultati dei tool
            risposta = chiama_con_retry(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[TOOL_DEFINITIONS],
                ),
            )

        mostra_stato()

if __name__ == "__main__":
    main()
