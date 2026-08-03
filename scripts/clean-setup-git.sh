#!/bin/bash -ex
export PC_TEST_ROOT="$(mktemp -d /tmp/gitmesh-agents-clean.XXXXXX)"
export PC_HOME="$PC_TEST_ROOT/home"
export PC_CACHE="$PC_TEST_ROOT/npm-cache"
export PC_DATA="$PC_TEST_ROOT/gitmesh-data"
mkdir -p "$PC_HOME" "$PC_CACHE" "$PC_DATA"
echo "PC_TEST_ROOT: $PC_TEST_ROOT"
echo "PC_HOME: $PC_HOME"
cd $PC_TEST_ROOT
GITMESH_REPO_URL="${GITMESH_REPO_URL:-https://github.com/LF-Decentralized-Trust-labs/gitmesh.git}"
git clone "$GITMESH_REPO_URL" repo
cd repo
pnpm install
env HOME="$PC_HOME" npm_config_cache="$PC_CACHE" npm_config_userconfig="$PC_HOME/.npmrc" \
  pnpm gitmesh-agents setup --yes --data-dir "$PC_DATA"
