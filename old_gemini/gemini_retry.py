"""
Utility per gestire il rate limit di Gemini (errore 429).
Usata da tutti e tre gli script della demo.
"""

import time
import re
from google.genai.errors import ClientError

# Colori condivisi (re-importati negli script principali, qui solo per i messaggi di retry)
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"


def _estrai_retry_delay(errore: ClientError) -> float:
    """Legge il suggerimento 'retry in Xs' dall'errore 429, default 30s."""
    testo = str(errore)
    match = re.search(r"retryDelay.*?'(\d+)s'", testo)
    if match:
        return float(match.group(1))
    # Fallback: cerca nel messaggio testuale
    match = re.search(r"retry in ([\d.]+)s", testo)
    if match:
        return float(match.group(1))
    return 30.0


def chiama_con_retry(fn, *args, max_tentativi=5, **kwargs):
    """
    Chiama fn(*args, **kwargs) ritentando su errore 429.
    Aspetta il tempo suggerito dall'API prima di riprovare.
    Solleva l'eccezione se supera max_tentativi o se l'errore non è 429.
    """
    for tentativo in range(1, max_tentativi + 1):
        try:
            return fn(*args, **kwargs)
        except ClientError as e:
            if "429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e):
                raise  # Errore diverso dal rate limit: non ritrentiamo

            attesa = _estrai_retry_delay(e)
            if tentativo == max_tentativi:
                print(f"\n{RED}[RATE LIMIT] Quota esaurita dopo {max_tentativi} tentativi. "
                      f"Controlla il piano su https://ai.dev/rate-limit{RESET}")
                raise

            print(f"\n{YELLOW}[RATE LIMIT] Quota API esaurita. "
                  f"Attendo {attesa:.0f}s prima di riprovare "
                  f"(tentativo {tentativo}/{max_tentativi})...{RESET}")
            time.sleep(attesa)
