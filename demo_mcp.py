"""
APPROCCIO 3: MCP con FastMCP + Groq
=====================================
Il server MCP (casse_server.py) gira come processo separato.
Questo client si connette via stdio, scopre i tool disponibili,
e li converte nel formato che Groq si aspetta (OpenAI-compatible).

Invece di definire i tool a mano nel codice (come nell'approccio 2),
li scopriamo dinamicamente dal server MCP. Il protocollo MCP fa da
intermediario standardizzato: il server non sa né gli importa
quale LLM c'è dall'altra parte (Groq, Gemini, OpenAI — tutto uguale).

Flusso:
  1. Client si connette al server MCP (subprocess stdio)
  2. Client chiede al server: "quali tool hai?"  → tool discovery
  3. Client converte i tool MCP → formato OpenAI/Groq
  4. Loop conversazione: come approccio 2, ma le tool call
     vengono inoltrate al server MCP invece di chiamare funzioni locali
"""

import os
import json
import asyncio
from groq import Groq
from fastmcp import Client as MCPClient
from fastmcp.client.transports import PythonStdioTransport #per la cmunucazine client-server, si potrebbe anche fare su una porta network

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

SYSTEM_PROMPT = """Sei un assistente per la gestione delle casse di un supermercato.
Hai a disposizione 4 casse, numerate da 0 a 3.
Usa i tool disponibili per aprire, chiudere o controllare lo stato delle casse.
Se l'utente chiede di agire su più casse (es. "tutte" o "le pari"), chiama il tool più volte.
Rispondi sempre in italiano, in modo conciso."""

# ─── Visualizzazione stato casse ─────────────────────────────────────────────

def mostra_stato_da_testo(testo: str):
    """Parsa la stringa da stato_tutte_casse() e la visualizza graficamente."""
    print(f"\n{CYAN}╔══════════════════════════════╗")
    for riga in testo.strip().split("\n"):
        if "APERTA" in riga:
            cassa = riga.split(":")[0].strip()
            print(f"║  {cassa}: 🟢 APERTA         ║")
        elif "CHIUSA" in riga:
            cassa = riga.split(":")[0].strip()
            print(f"║  {cassa}: 🔴 CHIUSA         ║")
    print(f"╚══════════════════════════════╝{RESET}\n")

# ─── Conversione tool MCP → formato OpenAI/Groq ──────────────────────────────

def mcp_tool_to_openai(mcp_tool) -> dict:
    """
    Converte un tool MCP (schema JSON standard) nel formato OpenAI/Groq.
    Questa è la traduzione tra i due protocolli — ed è tutto qui,
    poche righe di codice che abilitano l'interoperabilità.
    """
    input_schema = mcp_tool.inputSchema or {}
    return {
        "type": "function",
        "function": {
            "name": mcp_tool.name,
            "description": mcp_tool.description or "",
            "parameters": {
                "type": "object",
                "properties": input_schema.get("properties", {}),
                "required": input_schema.get("required", []),
            },
        },
    }

# ─── Loop conversazione asincrono ────────────────────────────────────────────

async def loop_conversazione(client_groq: Groq, mcp_client: MCPClient):
    # ── Tool discovery: chiediamo al server MCP quali tool espone ─────────────
    # In tutti gli altri approcci i tool erano hardcoded nel client.
    # Qui li scopriamo a runtime — potremmo connetterci a qualsiasi server MCP.
    print(f"{YELLOW}[MCP] Connessione al server... scoperta dei tool disponibili...{RESET}")
    mcp_tools_raw = await mcp_client.list_tools()

    print(f"{YELLOW}[MCP] Tool disponibili sul server:{RESET}")
    for t in mcp_tools_raw:
        print(f"  • {t.name}: {t.description}")
    print()

    # Convertiamo i tool MCP nel formato OpenAI/Groq
    groq_tools = [mcp_tool_to_openai(t) for t in mcp_tools_raw]

    print(f"{YELLOW}── TOOL DEFINITIONS (dopo conversione MCP → OpenAI/Groq) ───")
    print(json.dumps(groq_tools, ensure_ascii=False, indent=2))
    print(f"────────────────────────────────────────────────────────{RESET}\n")

    # Stato iniziale dal server MCP
    stato_iniziale = await mcp_client.call_tool("stato_tutte_casse", {})
    mostra_stato_da_testo(stato_iniziale.content[0].text)

    history = [{"role": "system", "content": SYSTEM_PROMPT}]

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

        risposta = client_groq.chat.completions.create(
            model=MODEL,
            messages=history,
            tools=groq_tools,
            tool_choice="auto",
        )

        # ── Loop tool call (struttura identica all'approccio 2) ───────────────
        while True:
            msg = risposta.choices[0].message
            finish_reason = risposta.choices[0].finish_reason

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
                print(f"{GREEN}Modello: {msg.content}{RESET}\n")
                break

            for tc in msg.tool_calls:
                nome = tc.function.name
                args = json.loads(tc.function.arguments)

                print(f"{MAGENTA}[MCP CALL] {nome}({args}){RESET}")

                # ── Qui la differenza chiave rispetto all'approccio 2: ─────────
                # Non chiamiamo una funzione Python locale, ma invochiamo
                # il tool sul server MCP via protocollo standardizzato.
                risultato_mcp = await mcp_client.call_tool(nome, args)
                risultato_testo = risultato_mcp.content[0].text

                print(f"{MAGENTA}[MCP RESULT] {risultato_testo}{RESET}")

                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": risultato_testo,
                })

            # Nuova chiamata al modello con i risultati dei tool
            risposta = client_groq.chat.completions.create(
                model=MODEL,
                messages=history,
                tools=groq_tools,
                tool_choice="auto",
            )

        # Stato aggiornato dal server MCP dopo ogni turno
        stato = await mcp_client.call_tool("stato_tutte_casse", {})
        mostra_stato_da_testo(stato.content[0].text)

# ─── Main ──────────────────────────────────────────────────────────────────────

async def main_async():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print(f"{RED}Errore: variabile d'ambiente GROQ_API_KEY non impostata.{RESET}")
        return

    client_groq = Groq(api_key=api_key)

    print(f"\n{BOLD}{'='*50}")
    print("  DEMO 3: MCP con FastMCP + Groq")
    print(f"{'='*50}{RESET}")
    print("Scrivi comandi in italiano per gestire le casse.\n")

    # Il server MCP viene lanciato come subprocess via trasporto stdio.
    # PythonStdioTransport lancia casse_server.py come processo figlio
    # e comunica con lui tramite stdin/stdout seguendo il protocollo MCP.
    server_path = os.path.join(os.path.dirname(__file__), "casse_server.py")
    async with MCPClient(PythonStdioTransport(server_path)) as mcp_client:
        await loop_conversazione(client_groq, mcp_client)

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()

"""
MCP da solo praticamente mi permette di definire funzioni python che divejtano tool,
in formato standardizzato - io poi conerto questo formato in quello specifico perhè
groq non ha il supporto nativo mcp, e groq mi ritorna nel suo formato i tool use,
e io devo "dispacchettare" dal suo formato i tool use e relativi parametri, e fare:
await mcp_[client.call](http://client.call)_tool("...", {})
che pratimcete la libreria mcp si arraangia a selezionare la funzione
e chiamrala (inoltra al server via stdio)
"""

"""
Con il SDK di Anthropic, il codice (questo, del client) sarebbe così:

import anthropic

client = anthropic.Anthropic()

response = client.beta.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Apri la cassa 2"}],
    mcp_servers=[
        {
            "type": "url",
            "url": "http://localhost:8000/mcp/",
            "name": "casse-server",
        }
    ],
    extra_headers={"anthropic-beta": "mcp-client-2025-04-04"},
)

print(response.content)

Il server MCP deve essere raggiungibile via HTTP (non stdio), quindi nel
casse_server.py lo lanceresti con:

mcp.run(transport="http", port=8000)

"""