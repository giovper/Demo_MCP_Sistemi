"""
APPROCCIO 1: Tag homemade nel testo
====================================
Il modello non ha strumenti nativi. Gli diciamo nel system prompt
di inserire tag speciali nel testo quando vuole agire.
Noi facciamo parsing dell'output con regex e agiamo di conseguenza.

LIMITE: comunicazione one-way. Il modello non sa se l'azione è riuscita.
        Se il modello scrive il tag in modo sbagliato, si rompe tutto.
"""

import os
import re
import json
from groq import Groq

# ─── Colori ANSI ─────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
BLUE    = "\033[94m"    # input utente
GREEN   = "\033[92m"    # output modello
YELLOW  = "\033[93m"    # JSON tecnici
CYAN    = "\033[96m"    # stato casse
RED     = "\033[91m"    # errori
MAGENTA = "\033[95m"    # azioni eseguite

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

def esegui_azioni(testo_modello: str):
    """
    Cerca nel testo del modello i tag <APRI X>, <CHIUDI X>, <STATO X>.
    Se il modello scrive il tag in modo sbagliato, non trova nulla.
    Questo è il punto debole dell'approccio: nessuna struttura garantita.
    """
    pattern = r"<(APRI|CHIUDI|STATO)\s+(\d|\*)>"
    trovati = re.findall(pattern, testo_modello, re.IGNORECASE)

    if not trovati:
        print(f"{MAGENTA}[PARSER] Nessun tag trovato nel testo del modello.{RESET}")
        return

    for azione, target in trovati:
        azione = azione.upper()
        indici = list(range(4)) if target == "*" else [int(target)]

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
IMPORTANTE: inserisci i tag esattamente come indicato, senza spazi extra o variazioni.
Sappi inoltre che ogni volta che scrivi un tag, esso viene eseguito in ogni caso, se scritto correttamente"""

#https://www.google.com/search?q=sequenze+numeriche+interessanti&sca_esv=097b722db578ca49&biw=1512&bih=802&sxsrf=ANbL-n6SyxU7BLsKf8T2YPFs6yY46eF8XQ%3A1777630711047&ei=9330aYjGAuaI9u8PtaSR4QI&ved=0ahUKEwjIncu47peUAxVmhP0HHTVSJCwQ4dUDCBM&uact=5&oq=sequenze+numeriche+interessanti&gs_lp=Egxnd3Mtd2l6LXNlcnAaAhgCIh9zZXF1ZW56ZSBudW1lcmljaGUgaW50ZXJlc3NhbnRpMgUQIRigAUjmMFDvBliEL3AEeAGQAQCYAa4BoAGLHqoBBTE1LjE4uAEDyAEA-AEBmAIloAKtH6gCEcICChAAGEcY1gQYsAPCAg0QABiABBiKBRhDGLADwgIKECMYgAQYigUYJ8ICChAAGIAEGIoFGEPCAgoQABiABBgUGIcCwgIFEAAYgATCAgcQIxiwAhgnwgIHEAAYgAQYDcICBxAjGOoCGCfCAg0QIxjwBRieBhjqAhgnwgINECMYngYY8AUY6gIYJ8ICChAjGOoCGCcYiwPCAhYQABiABBiKBRhDGOcGGOoCGLQC2AEBwgIQEAAYAxiPARjqAhi0AtgBAcICEBAuGAMYjwEY6gIYtALYAQHCAggQLhiABBixA8ICCxAuGIAEGLEDGIMBwgILEAAYgAQYsQMYgwHCAggQABiABBixA8ICCBAuGLEDGIAEwgIFEC4YgATCAg4QABiABBiKBRixAxiDAcICCBAAGIAEGMsBwgIGEAAYFhgewgIFEAAY7wXCAggQABiABBiiBMICBBAhGBWYAwfxBWZey97eXc8GiAYBkAYJugYGCAEQARgBkgcFMTYuMjGgB63JAbIHBTEyLjIxuAeaH8IHBzIuMTEuMjTIB26ACAE&sclient=gws-wiz-serp

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print(f"{RED}Errore: variabile d'ambiente GROQ_API_KEY non impostata.{RESET}")
        return

    client = Groq(api_key=api_key)

    print(f"\n{BOLD}{'='*50}")
    print("  DEMO 1: Approccio con Tag Homemade  [Groq]")
    print(f"{'='*50}{RESET}")
    print("Scrivi comandi in italiano per gestire le casse.")
    print("Es: 'apri la cassa 2', 'chiudi tutte', 'stato casse'\n")

    # Il system prompt va come primo messaggio con ruolo "system"
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

        # ── Chiamata al modello ────────────────────────────────────────────────
        risposta = client.chat.completions.create(
            model=MODEL,
            messages=history,
        )

        testo_risposta = risposta.choices[0].message.content

        # Aggiungiamo la risposta alla storia e stampiamo tutta la conversazione
        history.append({"role": "assistant", "content": testo_risposta})
        stampa_conversazione(history)

        print(f"{GREEN}Modello: {testo_risposta}{RESET}\n")

        # ── Parsing dei tag: il modello non riceverà mai conferma ─────────────
        esegui_azioni(testo_risposta)

        mostra_stato()

if __name__ == "__main__":
    main()
