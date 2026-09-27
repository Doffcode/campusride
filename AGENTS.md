# Instructions for every coding agent in this repo

1. Read `shared/CONTEXT.md` completely before doing anything.
2. Your launch prompt says which agent you are (A, B, C, or D). Read your task file in `tasks/` completely.
3. Edit ONLY your own folder: A → `dispatch/`, B → `backend/`, C → `voice/`, D → `frontend/`.
   `shared/`, `tasks/`, `acceptance/`, and the root files are read-only.
4. Run all commands from the repo root. Your acceptance test: `python -m pytest acceptance/test_<module>.py -q`.
5. If something in the contract or tests blocks you, write `<your_folder>/CONTRACT_ISSUE.md` and stop. Do not work around it.
6. Before you say you are done: run your acceptance tests, paste the final pytest summary line, and list every file you created.
