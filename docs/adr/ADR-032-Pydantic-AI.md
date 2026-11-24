# ADR-032: Pydantic AI come strato dei modelli (P1)

## Status
**Accepted** (2026-11-24, milestone P1 della roadmap, prima di R1 e `v1.0.0`)

## Context
- **Due adapter:** il motore parla ai modelli con l'SDK `openai` (`AsyncOpenAI`), attraverso:
  - `openai_adapter.py`, per l'API Responses di OpenAI;
  - `chat_completions_adapter.py`, per Chat Completions, usato da OpenRouter e dai server locali.
- **Codice morto:**
  - `groq_adapter.py` è un finto che risponde sempre la stessa frase;
  - `langchain_adapter.py` è un adapter legacy.

  Nessun percorso di produzione li usa.
- **Un provider nativo in più vuol dire un adapter in più da scrivere:** per esempio Anthropic, Gemini o Groq. In più ogni provider conta i token a modo suo.
- **LiteLLM non si usa** (decisione dell'utente del 2026-11-24). Le versioni 1.82.7 e 1.82.8 sono state compromesse su PyPI nel marzo 2026. Pydantic AI ha un provider `litellm`, ma qui non viene usato.

## Decision
**Opzione A: Pydantic AI solo come strato dei modelli.**

1. **Un solo adapter,** `adapters/pydantic_ai_adapter.py`. `PydanticAIAdapter.generate(context)` fa **una sola richiesta** al modello con `pydantic_ai.direct.model_request`, poi restituisce:
   - il testo;
   - le chiamate ai tool, come `ToolProposal`;
   - `usage` (token in entrata e in uscita);
   - `response_id`.
2. **Pydantic AI non esegue nessun tool.** `model_request` non ha un loop: riceve le definizioni dei tool (`ToolDefinition`) solo perché il modello possa proporli, e restituisce le chiamate come `ToolCallPart`. Il loop resta quello di A.U.R.O.R.A. e ogni tool passa dal Tool Gateway: policy, guardrail, schema, approvazioni, budget e audit.
3. **L'input si ricostruisce dal contesto durevole a ogni turno**, come prima. La costruzione dell'input diventa un modulo neutro rispetto al provider (`agent_engine/model_input.py`):
   - compito e correzioni del Critic;
   - i blocchi del Context Manager;
   - le osservazioni dei tool, ognuna preceduta dalla chiamata che l'ha prodotta;
   - l'avviso sui contenuti non affidabili.

   Così il cambio di provider a metà run continua a non rieseguire nessun tool.
4. **Provider:** `openai` (API Responses), `openrouter`, `local` (Ollama, LM Studio), e i nuovi `groq`, `anthropic` e `google` (Gemini).
   - Ognuno usa il suo modello di Pydantic AI:
     - `OpenAIResponsesModel` per OpenAI;
     - `OpenAIChatModel` per OpenRouter e per il server locale, sul loro indirizzo, come prima. `OpenRouterModel` rifiuta i nomi senza il prefisso del fornitore, che OpenRouter invece accetta, per esempio `openrouter/auto`;
     - `GroqModel`, `AnthropicModel` e `GoogleModel` per gli altri tre.
   - Le chiavi restano nel keyring, o nell'ambiente: `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`.
   - Un provider nuovo compare nell'editor dei modelli solo quando ha la sua chiave.
5. **Il resto del motore non cambia:**
   - routing per ruoli;
   - `FailoverProvider` e circuit breaker;
   - Critic diverso dall'Implementer;
   - Agent Budget, che riceve l'`usage` di Pydantic AI come riceveva quello dell'SDK.
6. **Dipendenze:**
   - `pydantic-ai-slim[openai,groq,anthropic,google]==2.66.0`: versione fissata, la più recente con almeno due settimane; solo gli extra dei provider usati, per tenere leggera l'installazione del desktop;
   - il minimo di `pydantic` sale a `>=2.12`, perché lo richiede Pydantic AI 2;
   - l'SDK `openai` resta, ma solo dentro Pydantic AI, e non si importa più nel codice di ÆHub.

**Scartata l'opzione B** (l'`Agent` di Pydantic AI con i tool rinviati). Ci sarebbero due loop da tenere d'accordo: approvazioni, ripresa con lo stesso `run_id`, Critic, budget e kill switch dovrebbero agganciarsi a quello di Pydantic AI. In più bisognerebbe dimostrare tool per tool che niente parte senza il Gateway. Con A questa garanzia c'è per costruzione.

## Consequences
- **Tolti:** `openai_adapter.py`, `chat_completions_adapter.py`, `groq_adapter.py`, `langchain_adapter.py`, `tests/unit/test_langchain_adapter.py` e `tests/unit/test_openai_adapter.py`. Al loro posto c'è `tests/unit/test_pydantic_ai_adapter.py`.
- **Test del motore:** approvazioni e ripresa, cambio di provider a metà run, circuit breaker e gli altri non cambiano le loro asserzioni. Cambiano solo i fake condivisi:
  - simulavano l'SDK `openai` sotto i vecchi adapter;
  - ora restituiscono oggetti veri dell'SDK (`Response`, `ChatCompletion`), che Pydantic AI legge come quelli della rete;
  - le richieste registrate restano quelle che il provider riceve davvero.
- **Eval:** il modello simulato delle eval (`evaluation/scripted.py`) misura i token sullo stesso input di prima, quindi il gate di release confronta numeri omogenei.
- **Schema:** nessuna modifica al database, quindi nessuna revisione Alembic.
- **Copertura:** i tre provider nuovi entrano in `docs/frontend-coverage.md`, nella riga 19 (modelli per ruolo) e nella 23 (chiavi).
