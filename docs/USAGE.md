# Usage

How to install UniBizKit and run the example applications. For the model format see [Backend.md](Backend.md); for the development workflow, ports and dev scripts see [Development.md](Development.md).

## Prerequisites

* Python 3.11+
* Node.js
* Docker (with Compose)

Installation instructions for each are in the [annexes](#annex-installing-the-prerequisites) below. The Supabase CLI is run automatically through `npx` with a pinned version — no separate install needed.

## Quick Start

```bash
# Clone and install
git clone https://github.com/unibizkit/unibizkit.git
cd unibizkit
python -m venv venv
source venv/bin/activate
pip install -e . -r requirements-dev.txt

# Select b2c-app as the second dev model. Alternative, to set it automatically
# in every shell: echo "export UBK_DEV_MODEL=b2c-app" > .envrc ; direnv allow
export UBK_DEV_MODEL=b2c-app

# Generate both applications, bring up their Supabase stacks and verify everything
pytest

# Start the b2c-app frontend
cd b2c-app/frontend
npm install
npm start     # http://localhost:3050/b2c/
```

The primary model (`models/test-app`) is served the same way from `test-app/frontend` at `http://localhost:3000/`.

Log in with the users seeded from the model's `security.jsonc` (listed in the generated `<app>/security_extended.json`).

## Doing It by Hand

`pytest` is the recommended path: it generates, deploys and verifies in one command. The equivalent manual steps for one application:

```bash
# Generate backend + frontend from the model in b2c-app output directory
uni-biz-kit models/b2c-app 

# Create/start the app's Supabase instance (writes backend/.env with URL and keys)
python b2c-app/bin/dev-supabase-start.py

# Load the generated schema and seed data
python b2c-app/bin/dev-supabase-reset-schema-and-data.py
```

Then start the frontend with `npm start` as above. The full list of `bin/dev-*` scripts is documented in [Development.md](Development.md).

## CLI Reference

```bash
uni-biz-kit path/to/model_dir                  # generate backend + frontend
uni-biz-kit --task validate path/to/model_dir  # validate the model only
uni-biz-kit path/to/model_dir --output-dir my-app
uni-biz-kit path/to/model_dir --skip-frontend
uni-biz-kit path/to/model_dir --skip-backend
```

## Generated Output

```
my-app/
├── backend/                  # SQL migrations, seed data, edge functions, Supabase config
├── frontend/                 # React-Admin application (Vite)
├── bin/                      # dev-* scripts to operate the local stack
├── concepts_extended.json    # enriched IR used by the generators
├── security_extended.json    # enriched security config (includes seeded users)
└── *_extended*.json          # other enriched configs and their schemas
```

See [Backend.md](Backend.md) and [Frontend.md](Frontend.md) for what each part contains.

## Testing

```bash
pytest                       # all tests
pytest tests/test_backend.py # SQL generation + database deployment
pytest tests/test_frontend.py# frontend generation + build
```

More detail in [Development.md](Development.md).

---

## Annex: Installing the Prerequisites

### Python

Use your distribution's Python 3.11+ package. Always create a virtual environment (`python -m venv venv`) as shown in the quick start.

### Docker

Install Docker and Docker Compose. For example, on Ubuntu:

```bash
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER
sudo init 6   # reboot so the group change applies
docker --version
```

### Node.js (via nvm)

```bash
# nvm https://github.com/nvm-sh/nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install --lts
npm --version
```

### direnv (optional)

[direnv](https://direnv.net/) loads `.envrc` automatically when entering the project directory, so `UBK_DEV_MODEL` is set in every shell without exporting it by hand.

```bash
sudo apt install -y direnv
# add to ~/.bashrc: eval "$(direnv hook bash)"
echo "export UBK_DEV_MODEL=b2c-app" > .envrc
direnv allow
```
