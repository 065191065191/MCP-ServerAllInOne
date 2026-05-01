#!/usr/bin/env bash
# Обёртка: установщик лежит в scripts/install.sh
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/install.sh" "$@"
