# ADR-031: Alembic come unica fonte dello schema (D1)

## Status
**Accepted** (2026-11-24, milestone D1 della roadmap, prima di P1)

## Context
- **Lo schema nasceva da `create_all`.** A ogni avvio `main.startup_db` creava l'estensione `vector` e chiamava `Base.metadata.create_all`. Alembic era configurato, ma senza nessuna revisione, e non era neppure tra le dipendenze.
- **`create_all` crea solo le tabelle che mancano: non cambia quelle che esistono.**
  - Per questo ogni campo nuovo finiva in una tabella a parte: `audit_chain`, `memory_chunks`, `monthly_spend`, `app_settings`, `imported_skills`.
  - L'alternativa era cancellare memoria, run e audit.
- **Il volume dei dati sopravvive ai rebuild:** `./data/postgres` in Docker, la cartella dei dati nell'app desktop. Con l'app desktop l'utente aggiorna senza sapere cosa c'è dentro, quindi l'aggiornamento dello schema deve essere automatico e non deve perdere righe.

## Decision
1. **Alembic è l'unica fonte dello schema.** Ogni modifica a un modello è una nuova revisione in `backend/alembic/versions/`, generata con `alembic revision --autogenerate` e poi riletta a mano. Niente più tabelle separate per aggirare `create_all`.
2. **Revisione `0001_baseline`:** le 17 tabelle di oggi, generate con `--autogenerate` su un database vuoto. In più contiene quello che `autogenerate` non vede:
   - l'estensione `vector`;
   - l'indice GIN `ix_memory_chunks_fts` su `to_tsvector('simple', content)`. Nei modelli è creato da un evento DDL, perché le eval su SQLite non hanno `to_tsvector`. `env.py` lo esclude dal confronto (`MANAGED_BY_HAND` in `app/core/migrations.py`).
3. **All'avvio `alembic upgrade head`** (`app/core/migrations.upgrade_database`), sulla connessione dell'API. Docker, `make demo` e il sidecar desktop passano tutti da `main.startup_db`; il bundle del desktop ora include `alembic/` e `alembic.ini`.
4. **Database creati con `create_all`** (tabelle presenti, `alembic_version` assente):
   - all'avvio vengono riconosciuti e se ne scrive un avviso nel log;
   - la baseline crea **solo le tabelle che mancano** e marca il database, poi girano le revisioni successive.

   **Differenza dalla roadmap:** la roadmap proponeva un `alembic stamp` della baseline. Uno stamp da solo lascerebbe senza tabelle un database di una versione più vecchia: per esempio uno di prima di F5, senza `imported_skills`. Per questo la baseline è idempotente: ogni tabella si crea solo se manca, e indice ed estensione usano `IF NOT EXISTS`. Il risultato è uno stamp più le tabelle mancanti.

   Funziona perché, fino a D1, nessuna colonna è mai stata aggiunta a una tabella esistente: le tabelle di un database vecchio hanno già la forma della baseline.
5. **Le eval** (`app/evaluation/engine.py`, SQLite in memoria) continuano con `create_all`: sono un database usa e getta.
6. **Comandi.** `env.py` legge `POSTGRES_URL` come l'API. Da `backend/` si usano:
   - `alembic upgrade head`;
   - `alembic revision --autogenerate -m "..."`;
   - `alembic check`.

## Consequences
- **Test in CI** (`tests/database/test_migrations.py`), su un database temporaneo accanto a `AEHUB_TEST_POSTGRES_URL`. In CI un Postgres irraggiungibile fa fallire i test invece di saltarli. I test controllano che:
  - lo schema creato da zero coincida con i modelli, cioè che `autogenerate` non trovi differenze;
  - un secondo avvio non cambi nulla;
  - un database `create_all` senza `imported_skills` e con delle righe venga marcato e aggiornato, senza perdere righe e con l'indice GIN funzionante;
  - le revisioni formino una sola linea;
  - nessun file del backend usi `create_all` tranne le eval.
- **Un modello cambiato senza revisione fa fallire la CI.** Verificato aggiungendo per prova una colonna: il test segnala `add_column`.
- **Nuova dipendenza:** `alembic>=1.20.1`, in `requirements.txt` e `requirements-desktop.txt`.
- **Facoltativo, non fatto in D1:** riunire le tabelle nate per aggirare `create_all`, per esempio `audit_chain` dentro `audit_logs`. Andrebbe fatto con una revisione che sposta le righe e ricostruisce la catena hash. Il guadagno è piccolo e il rischio sull'audit no, quindi resta un'idea per dopo, da decidere con l'utente.
- **Il downgrade della baseline** elimina tutto. Serve solo per i test e per un reset voluto.
