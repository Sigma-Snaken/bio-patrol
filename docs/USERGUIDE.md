# USER GUIDE

## QUICK START
1. Pull the repo from remote
```sh
# pull the repo (default: main branch)
git clone https://github.com/John-SC-Wu/kachaka_cmd_center.git

# show all branches (check the existence of the preferred branch)
git branch 
```

2. Checkout to specific branch
```sh
# newly-update for cron feature
git checkout feature/cron-scheduler

# main branch: latest version(2025-08-07) on-site verified
git checkout main

## ------ useful commands ------
# checkout to previous branch
git checkout -
# check the commit tags (on-site-verified-1.x) 
git tag
# check out to specific commit by tag
git checkout on-site-verified-1.2
```

3. Create python virtual environment (venv)
[install uv on Windows](https://docs.astral.sh/uv/getting-started/installation/)
```sh
# create virtual environment by uv
uv venv .venv # if `.venv` existed, removed it first.

# activate the virtual environment
.\.venv\Scripts\activate.ps1

# sync up package dependencies
uv sync

# launch the project 
python .\run.py
```

4. Project Configuration

* the config. file is located in `settings/.env.local`. The file is sensitive, so that it is preferred NOT to be within the project.
  - First time, it is better to change the config by using .env.example
  - On switching version, preserve the file `.env.local` first, and overwrite to updated  project version
