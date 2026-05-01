"""
APPROCCIO 1: Tag homemade nel testo
====================================
Il modello non ha strumenti nativi. Gli diciamo nel system prompt
di inserire tag speciali nel testo quando vuole agire.
Noi facciamo parsing con regex e agiamo di conseguenza.

LIMITE: comunicazione one-way. Il modello non sa se l'azione è riuscita.
"""

import os
import re
import json
import google.genai as genai
from gemini_retry import chiama_con_retry

# ─── Colori ANSI ─────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
BLUE    = "\033[94m"    # input utente
GREEN   = "\033[92m"    # output modello
YELLOW  = "\033[93m"    # JSON tecnici
CYAN    = "\033[96m"    # stato casse
RED     = "\033[91m"    # errori / casse chiuse
MAGENTA = "\033[95m"    # azioni eseguite

# ─── Stato casse (locale, in memoria) ─────────────────────────────────────────
# True = aperta, False = chiusa
casse = [False, False, False, False]

def mostra_stato():
    """Stampa lo stato visivo delle 4 casse."""
    print(f"\n{CYAN}╔══════════════════════════════╗")
    for i, aperta in enumerate(casse):
        if aperta:
            print(f"║  CASSA {i}: 🟢 APERTA         ║")
        else:
            print(f"║  CASSA {i}: 🔴 CHIUSA         ║")
    print(f"╚══════════════════════════════╝{RESET}\n")

def esegui_azioni(testo_modello: str):
    """
    Cerca nel testo del modello i tag <APRI X>, <CHIUDI X>, <STATO X>.
    Esegue le azioni corrispondenti.
    Se il modello scrive il tag in modo sbagliato, non funziona nulla.
    """
    # Regex che cerca i tag nel formato atteso
    pattern = r"<(APRI|CHIUDI|STATO)\s+(\d|\*)>"
    trovati = re.findall(pattern, testo_modello, re.IGNORECASE)

    if not trovati:
        print(f"{MAGENTA}[PARSER] Nessun tag trovato nel testo del modello.{RESET}")
        return

    for azione, target in trovati:
        azione = azione.upper()

        # Determina quali casse coinvolgere
        if target == "*":
            indici = list(range(4))
        else:
            indici = [int(target)]

        for i in indici:
            if azione == "APRI":
                casse[i] = True
                print(f"{MAGENTA}[AZIONE] Cassa {i} → APERTA{RESET}")
            elif azione == "CHIUDI":
                casse[i] = False
                print(f"{MAGENTA}[AZIONE] Cassa {i} → CHIUSA{RESET}")
            elif azione == "STATO":
                stato = "APERTA" if casse[i] else "CHIUSA"
                print(f"{MAGENTA}[AZIONE] Stato cassa {i}: {stato}{RESET}")

# ─── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Sei un assistente per la gestione delle casse di un supermercato.
Hai a disposizione 4 casse, numerate da 0 a 3.

Quando devi compiere un'azione, inserisci nel tuo testo uno dei seguenti tag:
- <APRI X>   per aprire la cassa X (es. <APRI 2>)
- <CHIUDI X> per chiudere la cassa X (es. <CHIUDI 1>)
- <STATO X>  per mostrare lo stato della cassa X (es. <STATO 0>)

Usa * al posto del numero per agire su tutte le casse (es. <APRI *>).

Puoi usare più tag nella stessa risposta.
Rispondi sempre in italiano, in modo conciso.
IMPORTANTE: inserisci i tag esattamente come indicato, senza spazi extra o variazioni."""

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(f"{RED}Errore: variabile d'ambiente GEMINI_API_KEY non impostata.{RESET}")
        return

    client = genai.Client(api_key=api_key)

    print(f"\n{BOLD}{'='*50}")
    print("  DEMO 1: Approccio con Tag Homemade")
    print(f"{'='*50}{RESET}")
    print("Scrivi comandi in italiano per gestire le casse.")
    print("Es: 'apri la cassa 2', 'chiudi tutte', 'stato casse'\n")

    # Cronologia della conversazione (mantenuta tra i turni)
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

        # Aggiungiamo il messaggio dell'utente alla storia
        history.append({"role": "user", "parts": [{"text": utente}]})

        # ── Mostriamo il JSON che mandiamo al modello ──────────────────────────
        payload = {
            "model": "gemini-2.0-flash",
            "system_instruction": SYSTEM_PROMPT,
            "contents": history,
        }
        print(f"\n{YELLOW}── REQUEST JSON ─────────────────────────────")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"─────────────────────────────────────────────{RESET}\n")

        # ── Chiamata al modello (con retry automatico su 429) ─────────────────
        risposta = chiama_con_retry(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents=history,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
            ),
        )

        testo_risposta = risposta.text

        # ── Mostriamo il JSON di risposta ──────────────────────────────────────
        resp_json = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": testo_risposta}]
                    },
                    "finish_reason": str(risposta.candidates[0].finish_reason),
                }
            ]
        }
        print(f"{YELLOW}── RESPONSE JSON ────────────────────────────")
        print(json.dumps(resp_json, ensure_ascii=False, indent=2))
        print(f"─────────────────────────────────────────────{RESET}\n")

        # ── Output del modello ─────────────────────────────────────────────────
        print(f"{GREEN}Modello: {testo_risposta}{RESET}\n")

        # ── Parsing dei tag e azioni ───────────────────────────────────────────
        # Il modello non riceverà mai conferma: questa è la debolezza dell'approccio
        esegui_azioni(testo_risposta)

        # Aggiungiamo la risposta alla storia
        history.append({"role": "model", "parts": [{"text": testo_risposta}]})

        mostra_stato()

if __name__ == "__main__":
    main()
