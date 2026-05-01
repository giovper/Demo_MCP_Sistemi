# MCP e i diversi provider: chi fa il lavoro?

Il server MCP è sempre lo stesso. Scrivi `casse_server.py` una volta e quello funziona a prescindere da chi c'è dall'altra parte. La differenza sta tutta nel **client** — cioè in quanto lavoro devi fare tu per collegare il server MCP al modello.

## Provider con supporto MCP nativo (Anthropic, Google Gemini)

Il SDK di questi provider sa già parlare MCP. Tu gli dici "ecco il server" e lui fa tutto da solo:

- Si connette al server MCP
- Chiede quali tool sono disponibili (discovery)
- Li converte nel formato interno del modello
- Quando il modello vuole usare un tool, inoltra la chiamata al server
- Riceve il risultato e lo rimanda al modello

Il codice del client è banale — poche righe. Con Anthropic gli passi l'URL del server MCP direttamente nella chiamata API. Con Gemini gli passi la sessione del client MCP come parametro `tools`. In entrambi i casi, non devi scrivere nessuna logica di collegamento.

## Provider senza supporto MCP nativo (Groq, OpenAI)

Il SDK di questi provider non sa cosa sia MCP. Sa solo ricevere definizioni di tool nel proprio formato (il formato OpenAI) e rispondere con richieste di invocazione. Tutto il resto lo devi fare tu:

1. **Connessione al server MCP** — usi la libreria `fastmcp` per connetterti al server
2. **Discovery** — chiedi al server la lista dei tool disponibili
3. **Conversione** — traduci le definizioni dei tool dal formato MCP al formato OpenAI (sono simili ma non identici: cambia la struttura del JSON)
4. **Inoltro delle chiamate** — quando il modello risponde con una tool call, prendi il nome e i parametri e chiami `mcp_client.call_tool()` manualmente
5. **Restituzione dei risultati** — prendi la risposta dal server MCP e la rimandi al modello come messaggio con ruolo `tool`

In pratica, stai scrivendo a mano tutto il codice di collegamento che nei SDK nativi è già incluso.

## Perché questo è rilevante

Questa differenza è esattamente il problema che MCP vuole risolvere. Se ogni provider adottasse MCP nel proprio SDK, scrivere un client sarebbe ugualmente semplice ovunque. Un server MCP scritto una volta funzionerebbe con qualsiasi modello senza adattamenti.

Oggi siamo in una fase di transizione: alcuni provider (Anthropic, Google) hanno già integrato il supporto, altri (OpenAI, Groq) non ancora. Per chi usa questi ultimi, il codice extra da scrivere non è tanto — una ventina di righe — ma è codice che non dovresti dover scrivere, e che va adattato se il formato del provider cambia. È il vecchio problema N×M in scala ridotta: non più "un'integrazione per ogni coppia modello-servizio", ma almeno "un adattatore per ogni formato di provider che non supporta MCP".

Man mano che lo standard viene adottato più ampiamente, questo problema si riduce fino a scomparire.