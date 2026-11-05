UV ?= $(shell command -v uv || echo $(HOME)/.local/bin/uv)
PY := .venv/bin/python
DOTNET ?= $(shell [ -x $(HOME)/.dotnet/dotnet ] && echo $(HOME)/.dotnet/dotnet || command -v dotnet)

.PHONY: setup seed up test demo-e2e screenshots video dff check-dotnet

setup: check-dotnet ## Dependencias Python, navegador de Playwright y paquetes NuGet del proyecto de tests
	$(UV) sync
	$(PY) -m playwright install chromium
	cd sample_data/test-repo-seed && $(DOTNET) build -nologo -v q && rm -rf bin obj

check-dotnet:
	@$(DOTNET) --list-sdks | grep -q '^8\.' || (echo "Hace falta el SDK de .NET 8 (ver README)"; exit 1)

seed: ## Deja el entorno de demo en su estado inicial (con los servicios parados)
	$(PY) scripts/seed.py

up: ## Arranca web bajo prueba (:8602), Azure DevOps simulado (:8601) y el asistente (:8600)
	@[ -f .data/azure-mock.json ] || $(PY) scripts/seed.py
	.venv/bin/honcho start

test: ## Tests unitarios y de contrato
	$(PY) -m pytest -q

demo-e2e: ## Recorre el flujo completo sin UI (con `make up` en otra terminal)
	$(PY) scripts/demo_e2e.py

screenshots: ## Capturas de las pantallas en docs/capturas (con `make up` en marcha)
	$(PY) scripts/screenshots.py

video: ## Vídeo de la demo en docs/video (con `make up` en marcha sobre un `make seed` reciente)
	$(UV) run --with imageio-ffmpeg python scripts/record_demo.py

dff: ## Regenera los DFF de ejemplo
	$(PY) sample_data/dff/build_dff.py
