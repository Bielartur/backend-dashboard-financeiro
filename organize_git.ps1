# Script para organizar alterações em branches e commits semânticos

$originalBranch = (git rev-parse --abbrev-ref HEAD).Trim()
Write-Host "Branch atual detectada: $originalBranch"

Write-Host "Iniciando organização das alterações..."

# 1. Configuração de Banco de Dados e Entidades
Write-Host "`n[1/4] Processando alterações de Banco de Dados..."
git checkout -b fix/database-config
git add src/entities/merchant_alias.py src/entities/open_finance_account.py src/entities/open_finance_item.py alembic/env.py main.py
git commit -m "fix(db): adicionar defaults de server-side para timestamps e UUIDs e garantir criação de tabelas"

# Voltar para a branch original
git checkout $originalBranch

# 2. Testes do Dashboard
Write-Host "`n[2/4] Processando testes do Dashboard..."
git checkout -b feat/dashboard-tests
git add tests/dashboard/
git commit -m "test(dashboard): adicionar testes de exclusão de cartão de crédito e lógica de status de gastos"

# Voltar para a branch original
git checkout $originalBranch

# 3. Dependências do Projeto
Write-Host "`n[3/4] Processando dependências..."
git checkout -b chore/update-dependencies
git add pyproject.toml uv.lock
git commit -m "chore: atualizar dependências do projeto (pluggy-sdk, cachetools)"

# Voltar para a branch original
git checkout $originalBranch

# 4. Testes de Transações e Outros Arquivos Novos
Write-Host "`n[4/4] Processando novos testes de transações..."
git checkout -b test/transactions-setup
git add tests/transactions/
git commit -m "test(transactions): adicionar estrutura inicial de testes de transação e controller"

# Voltar para a branch original
git checkout $originalBranch

Write-Host "`n---------------------------------------------------"
Write-Host "Organização concluída com sucesso!"
Write-Host "As seguintes branches foram criadas:"
Write-Host "- fix/database-config"
Write-Host "- feat/dashboard-tests"
Write-Host "- chore/update-dependencies"
Write-Host "- test/transactions-setup"
Write-Host "---------------------------------------------------"
