import os
import json
import anthropic

# ─── Colori ANSI ─────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
BLUE    = "\033[94m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
RED     = "\033[91m"
MAGENTA = "\033[95m"

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """Sei un assistente per la gestione delle casse di un supermercato.
Hai a disposizione 4 casse, numerate da 0 a 3.
Usa i tool disponibili per aprire, chiudere o controllare lo stato delle casse.
Se l'utente chiede di agire su più casse (es. "tutte" o "le pari"), chiama il tool più volte.
Rispondi sempre in italiano, in modo conciso."""

# ─── Visualizzazione stato casse ─────────────────────────────────────────────

def mostra_stato_da_risposta(response):
    """
    Cerca nei blocchi della risposta il risultato di stato_tutte_casse
    e lo visualizza graficamente. Se non lo trova, chiede lo stato esplicitamente.
    """
    for block in response.content:
        if hasattr(block, 'text') and block.type == "text":
            testo = block.text
            if "APERTA" in testo or "CHIUSA" in testo:
                mostra_stato_da_testo(testo)
                return

def mostra_stato_da_testo(testo: str):
    print(f"\n{CYAN}╔══════════════════════════════╗")
    for riga in testo.strip().split("\n"):
        if "APERTA" in riga:
            cassa = riga.split(":")[0].strip()
            print(f"║  {cassa}: 🟢 APERTA         ║")
        elif "CHIUSA" in riga:
            cassa = riga.split(":")[0].strip()
            print(f"║  {cassa}: 🔴 CHIUSA         ║")
    print(f"╚══════════════════════════════╝{RESET}\n")

def stampa_risposta(response):
    """Stampa i blocchi della risposta colorati per tipo."""
    print(f"\n{YELLOW}── RISPOSTA API ─────────────────────────────")
    for block in response.content:
        if block.type == "text":
            print(f"  {GREEN}[text] {block.text}{RESET}")
        elif block.type == "tool_use":
            print(f"  {MAGENTA}[tool_use] {block.name}({json.dumps(block.input, ensure_ascii=False)}){RESET}")
        elif block.type == "mcp_tool_use":
            # Quando il SDK chiama un tool MCP, genera questo tipo di blocco
            print(f"  {MAGENTA}[mcp_tool_use] {block.name}({json.dumps(block.input, ensure_ascii=False)}){RESET}")
        elif block.type == "mcp_tool_result":
            # Il risultato dal server MCP, gestito automaticamente dal SDK
            content_text = ""
            if hasattr(block, 'content') and block.content:
                for c in block.content:
                    if hasattr(c, 'text'):
                        content_text = c.text
            print(f"  {MAGENTA}[mcp_tool_result] {content_text}{RESET}")
    print(f"─────────────────────────────────────────────{RESET}\n")

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(f"{RED}Errore: variabile d'ambiente ANTHROPIC_API_KEY non impostata.{RESET}")
        return

    client = anthropic.Anthropic()

    print(f"\n{BOLD}{'='*50}")
    print("  DEMO 3: MCP con SDK Anthropic")
    print(f"{'='*50}{RESET}")
    print("Scrivi comandi in italiano per gestire le casse.\n")

    # configurazione MCP necessaria ─ decisamente + semplice

    mcp_servers = [
        {
            "type": "url",
            "url": "http://localhost:8000/mcp/",
            "name": "casse-supermercato",
        }
    ]

    messages = []

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "Mostrami lo stato di tutte le casse."}],
        mcp_servers=mcp_servers,
        extra_headers={"anthropic-beta": "mcp-client-2025-04-04"},
    )
    stampa_risposta(response)
    mostra_stato_da_risposta(response)

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

        messages.append({"role": "user", "content": utente})

        # ── Questa singola chiamata fa TUTTO: ─────────────────────────────────
        # 1. Manda il messaggio al modello
        # 2. Il modello decide di usare un tool MCP
        # 3. Il SDK chiama il server MCP automaticamente
        # 4. Il risultato torna al modello
        # 5. Il modello genera la risposta finale
        #
        # Noi non vediamo e non gestiamo nessuno di questi passaggi intermedi - a differenza di prima
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
            mcp_servers=mcp_servers,
            extra_headers={"anthropic-beta": "mcp-client-2025-04-04"},
        )

        #Esattamente, può durare anche diversi secondi, 
        # Quella singola chiamata potrebbe durare diversi secondi perché dentro
        # ci sono più round-trip nascosti: il SDK si connette al server MCP, scopre
        # i tool, manda il prompt al modello, il modello decide di usare un tool, il
        # SDK chiama il server MCP, aspetta il risultato, lo rimanda al modello, il
        # modello magari chiama un altro tool, e così via fino alla risposta finale

        stampa_risposta(response)

        # Estraiamo il testo finale dalla risposta
        testo_finale = ""
        for block in response.content:
            if hasattr(block, 'text') and block.type == "text":
                testo_finale += block.text

        if testo_finale:
            print(f"{GREEN}Modello: {testo_finale}{RESET}\n")
            messages.append({"role": "assistant", "content": testo_finale})

        # Aggiorniamo lo stato visivo
        stato_response = client.beta.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": "Dimmi lo stato di tutte le casse."}],
            mcp_servers=mcp_servers,
            extra_headers={"anthropic-beta": "mcp-client-2025-04-04"},
        )
        mostra_stato_da_risposta(stato_response)


if __name__ == "__main__":
    main()


"""
IMPORTANTI CHIARIMENTI

la Responses API di Groq supporta solo server MCP remoti via HTTPS, non localhost
stdio. Il tuo casse_server.py gira in locale via stdio. Per usare la Responses API
dovresti esporre il server via HTTP su un URL raggiungibile da Groq (i loro server
devono poterci parlare, non basta localhost).

E no, il codice demo_mcp_con_supporto_anthropic.py non ha lo stesso problema. Il SDK
di anthropic (e altri) se ne occupano
"""

"""
In merito a json RCP:

quindi json rcp agisce solo nella comunicazione tra il server di anthropic
(che elabora il mio prompt ed eventaulemnte usa i tool attraverso json rcp)
(oppure se il sdk non ha il supporto nativo completo per mcp, il server ritorna un
json con anche dei tool_use,  e il mio codice li deve despacchettare e chiamare lui
i tool con json rcp) , mentre in tool use specifico api sdk, dato che avviene tutto
sul mio pc, non serve??
"""