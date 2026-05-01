"""
Utility per gestire il rate limit di Groq (errore 429).
Usata da tutti e tre gli script della demo.
"""

import re
import time
from groq import RateLimitError

YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"


def _estrai_attesa(errore: RateLimitError) -> float:
    """Legge il suggerimento 'try again in Xs' dal messaggio di errore, default 15s."""
    match = re.search(r"try again in ([\d.]+)s", str(errore), re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 15.0


def chiama_con_retry(fn, *args, max_tentativi=5, **kwargs):
    """
    Chiama fn(*args, **kwargs) ritentando su errore 429 (rate limit).
    Aspetta il tempo suggerito dall'API prima di riprovare.
    """
    for tentativo in range(1, max_tentativi + 1):
        try:
            return fn(*args, **kwargs)
        except RateLimitError as e:
            if tentativo == max_tentativi:
                print(f"\n{RED}[RATE LIMIT] Quota esaurita dopo {max_tentativi} tentativi.{RESET}")
                raise
            attesa = _estrai_attesa(e)
            print(f"\n{YELLOW}[RATE LIMIT] Troppe richieste. "
                  f"Attendo {attesa:.0f}s prima di riprovare "
                  f"(tentativo {tentativo}/{max_tentativi})...{RESET}")
            time.sleep(attesa)
