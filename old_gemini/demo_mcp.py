"""
APPROCCIO 3: MCP con FastMCP + Gemini SDK
==========================================
Il server MCP (casse_server.py) gira come processo separato.
Questo client si connette via stdio e ottiene la lista dei tool disponibili.

Invece di definire i tool a mano nel codice (come nell'approccio 2),
li scopriamo dinamicamente dal server MCP e li convertiamo nel formato
che Gemini si aspetta. Il protocollo MCP fa da intermediario standardizzato.

Flusso:
  1. Client si connette al server MCP (subprocess stdio)
  2. Client chiede al server: "quali tool hai?"
  3. Client converte i tool MCP → function_declarations Gemini
  4. Loop conversazione: come approccio 2, ma le tool call
     vengono inoltrate al server MCP invece di chiamare funzioni locali
"""

import os
import sys
import json
import asyncio
import subprocess
import google.genai as genai
import google.genai.types as types
from fastmcp import Client as MCPClient
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

SYSTEM_PROMPT = """Sei un assistente per la gestione delle casse di un supermercato.
Hai a disposizione 4 casse, numerate da 0 a 3.
Usa i tool disponibili per aprire, chiudere o controllare lo stato delle casse.
Se l'utente chiede di agire su più casse (es. "tutte" o "le pari"), chiama il tool più volte.
Rispondi sempre in italiano, in modo conciso."""

# ─── Funzioni di visualizzazione ─────────────────────────────────────────────

def mostra_stato_da_testo(testo_stato: str):
    """
    Legge la stringa restituita da stato_tutte_casse() e la visualizza.
    Es. "Cassa 0: APERTA\nCassa 1: CHIUSA\n..."
    """
    print(f"\n{CYAN}╔══════════════════════════════╗")
    for riga in testo_stato.strip().split("\n"):
        if "APERTA" in riga:
            cassa = riga.split(":")[0].strip()
            print(f"║  {cassa}: 🟢 APERTA         ║")
        elif "CHIUSA" in riga:
            cassa = riga.split(":")[0].strip()
            print(f"║  {cassa}: 🔴 CHIUSA         ║")
    print(f"╚══════════════════════════════╝{RESET}\n")

# ─── Conversione tool MCP → Gemini ───────────────────────────────────────────

def mcp_tool_to_gemini(mcp_tool) -> types.FunctionDeclaration:
    """
    Converte un tool MCP (con schema JSON standard) in un FunctionDeclaration
    di Gemini. Questa è la traduzione tra i due protocolli.
    """
    input_schema = mcp_tool.inputSchema or {}
    properties_raw = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    # Traduciamo ogni parametro nel tipo Gemini corrispondente
    TYPE_MAP = {
        "integer": types.Type.INTEGER,
        "string":  types.Type.STRING,
        "boolean": types.Type.BOOLEAN,
        "number":  types.Type.NUMBER,
    }

    properties = {}
    for nome_param, schema_param in properties_raw.items():
        tipo_json = schema_param.get("type", "string")
        properties[nome_param] = types.Schema(
            type=TYPE_MAP.get(tipo_json, types.Type.STRING),
            description=schema_param.get("description", ""),
        )

    params = types.Schema(
        type=types.Type.OBJECT,
        properties=properties,
        required=required,
    ) if properties else None

    return types.FunctionDeclaration(
        name=mcp_tool.name,
        description=mcp_tool.description or "",
        parameters=params,
    )

# ─── Loop conversazione asincrono ────────────────────────────────────────────

async def loop_conversazione(client_gemini: genai.Client, mcp_client: MCPClient):
    """
    Gestisce la conversazione con l'utente.
    Scopre i tool dal server MCP, poi avvia il loop di chat.
    """
    # ── Scoperta dei tool dal server MCP ──────────────────────────────────────
    # A differenza dell'approccio 2, non sappiamo a priori quali tool esistono.
    # Li chiediamo al server MCP dinamicamente.
    print(f"{YELLOW}[MCP] Connessione al server... scoperta dei tool disponibili...{RESET}")
    mcp_tools_raw = await mcp_client.list_tools()

    print(f"{YELLOW}[MCP] Tool disponibili sul server:{RESET}")
    for t in mcp_tools_raw:
        print(f"  • {t.name}: {t.description}")
    print()

    # Convertiamo i tool MCP nel formato Gemini
    gemini_tool_declarations = [mcp_tool_to_gemini(t) for t in mcp_tools_raw]
    gemini_tools = types.Tool(function_declarations=gemini_tool_declarations)

    print(f"{YELLOW}── TOOL DEFINITIONS (dopo conversione MCP→Gemini) ──────────")
    for fd in gemini_tool_declarations:
        print(json.dumps({
            "name": fd.name,
            "description": fd.description,
            "parameters": str(fd.parameters),
        }, ensure_ascii=False, indent=2))
    print(f"────────────────────────────────────────────────────────{RESET}\n")

    # Recuperiamo lo stato iniziale delle casse dal server
    stato_iniziale = await mcp_client.call_tool("stato_tutte_casse", {})
    mostra_stato_da_testo(stato_iniziale.content[0].text)

    history = []

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

        # ── Chiamata al modello ────────────────────────────────────────────────
        print(f"\n{YELLOW}── REQUEST ──────────────────────────────────")
        print(json.dumps({"contents": [{"role": c.role, "parts_count": len(c.parts)} for c in history]}, ensure_ascii=False, indent=2))
        print(f"─────────────────────────────────────────────{RESET}\n")

        risposta = chiama_con_retry(
            client_gemini.models.generate_content,
            model="gemini-2.0-flash",
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[gemini_tools],
            ),
        )

        # ── Loop tool call (identico all'approccio 2 nella struttura) ─────────
        while True:
            candidate = risposta.candidates[0]
            parts_risposta = candidate.content.parts

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

            tool_calls = [p for p in parts_risposta if p.function_call]

            if not tool_calls:
                testo_finale = "".join(p.text for p in parts_risposta if p.text)
                print(f"{GREEN}Modello: {testo_finale}{RESET}\n")
                history.append(candidate.content)
                break

            history.append(candidate.content)
            risultati_parts = []

            for part in tool_calls:
                fc = part.function_call
                nome_funzione = fc.name
                args = dict(fc.args)

                print(f"{MAGENTA}[MCP CALL] {nome_funzione}({args}){RESET}")

                # ── Qui la differenza chiave rispetto all'approccio 2: ─────────
                # Non chiamiamo una funzione Python locale, ma invochiamo
                # il tool sul server MCP via protocollo standardizzato.
                risultato_mcp = await mcp_client.call_tool(nome_funzione, args)
                risultato_testo = risultato_mcp.content[0].text

                print(f"{MAGENTA}[MCP RESULT] {risultato_testo}{RESET}")

                risultati_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=nome_funzione,
                            response={"result": risultato_testo},
                        )
                    )
                )

            history.append(types.Content(role="user", parts=risultati_parts))

            risposta = chiama_con_retry(
                client_gemini.models.generate_content,
                model="gemini-2.0-flash",
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[gemini_tools],
                ),
            )

        # Recuperiamo lo stato aggiornato dal server MCP
        stato = await mcp_client.call_tool("stato_tutte_casse", {})
        mostra_stato_da_testo(stato.content[0].text)


# ─── Main ──────────────────────────────────────────────────────────────────────

async def main_async():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(f"{RED}Errore: variabile d'ambiente GEMINI_API_KEY non impostata.{RESET}")
        return

    client_gemini = genai.Client(api_key=api_key)

    print(f"\n{BOLD}{'='*50}")
    print("  DEMO 3: MCP con FastMCP + Gemini")
    print(f"{'='*50}{RESET}")
    print("Scrivi comandi in italiano per gestire le casse.\n")

    # Il server MCP viene lanciato come subprocess. fastmcp.Client gestisce
    # il trasporto stdio automaticamente: parla MCP con il processo figlio.
    server_path = os.path.join(os.path.dirname(__file__), "casse_server.py")
    async with MCPClient(["python", server_path]) as mcp_client:
        await loop_conversazione(client_gemini, mcp_client)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
