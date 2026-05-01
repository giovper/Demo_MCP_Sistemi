"""
MCP SERVER: casse_server.py
============================
Questo è il server MCP che espone i tool per gestire le casse.
Viene lanciato come subprocess da demo_mcp.py via trasporto stdio.

Il server mantiene lo stato delle casse in memoria.
Espone 4 tool al client MCP:
  - apri_cassa(numero)
  - chiudi_cassa(numero)
  - stato_cassa(numero)
  - stato_tutte_casse()
"""

from fastmcp import FastMCP

# Stato delle casse: True = aperta, False = chiusa
casse = [False, False, False, False]

# Creiamo il server MCP con un nome descrittivo
mcp = FastMCP("Gestione Casse Supermercato")


@mcp.tool()
def apri_cassa(numero: int) -> str:
    """Apre una cassa del supermercato rendendola operativa."""
    if not 0 <= numero <= 3:
        return f"Errore: cassa {numero} non esiste. Le casse valide sono 0, 1, 2, 3."
    casse[numero] = True
    return f"Cassa {numero} aperta con successo."


@mcp.tool()
def chiudi_cassa(numero: int) -> str:
    """Chiude una cassa del supermercato."""
    if not 0 <= numero <= 3:
        return f"Errore: cassa {numero} non esiste. Le casse valide sono 0, 1, 2, 3."
    casse[numero] = False
    return f"Cassa {numero} chiusa con successo."


@mcp.tool()
def stato_cassa(numero: int) -> str:
    """Controlla se una cassa specifica è aperta o chiusa."""
    if not 0 <= numero <= 3:
        return f"Errore: cassa {numero} non esiste."
    stato = "aperta" if casse[numero] else "chiusa"
    return f"Cassa {numero} è attualmente {stato}."


@mcp.tool()
def stato_tutte_casse() -> str:
    """Restituisce lo stato di tutte e 4 le casse del supermercato."""
    righe = []
    for i, aperta in enumerate(casse):
        stato = "APERTA" if aperta else "CHIUSA"
        righe.append(f"Cassa {i}: {stato}")
    return "\n".join(righe)


if __name__ == "__main__":
    # Avvia il server in modalità stdio (standard per MCP con subprocess)
    mcp.run(transport="stdio")
