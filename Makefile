.PHONY: generate clean test help

PROTO_DIR := proto
OUTPUT_DIR := src/humex/proto
PYTHON := python3

help:
	@echo "Available targets:"
	@echo "  make generate - Regenerate Python protobuf files from proto/*.proto"
	@echo "  make clean    - Remove generated protobuf files and pycaches"
	@echo "  make test     - Run pytest"

generate:
	$(PYTHON) scripts/generate_pb2.py

clean:
	find $(OUTPUT_DIR) -name "*_pb2.py" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

test:
	pytest tests/

.DEFAULT_GOAL := help
