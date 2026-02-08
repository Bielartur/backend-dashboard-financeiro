# Script de Reestruturação de Git (v2) - Stacked Branches
# Este script organiza as alterações atuais em uma sequência lógica de branches e commits.

$originalBranch = (git rev-parse --abbrev-ref HEAD).Trim()
Write-Host "Branch Base Detectada: $originalBranch" -ForegroundColor Cyan

# Função auxiliar para checkout, add e commit seguro
function Create-Commit {
    param (
        [string]$branchName,
        [string[]]$files,
        [string]$message
    )
    
    Write-Host "`n---------------------------------------------------"
    Write-Host "Processando: $branchName" -ForegroundColor Yellow
    
    # Cria a branch a partir do estado ATUAL (acumula mudanças anteriores se já esteve em outra branch recém-criada, mas como é script linear, funciona como pilha)
    # Na primeira chamada, baseia-se na original. Nas seguintes, baseia-se na anterior.
    git checkout -b $branchName
    
    foreach ($file in $files) {
        if (Test-Path $file) {
            git add $file
        } else {
            # Tenta adicionar mesmo se não existir (para arquivos deletados)
            git add $file 2>$null
        }
    }
    
    # Tratamento especial para diretórios que podem não existir ou serem untracked
    foreach ($file in $files) {
         if ($file -match "/$") { # Se termina com /, assume diretório
             git add $file 2>$null
         }
    }
    
    # Verifica se há algo para commitar
    $status = git status --porcelain
    if ($status) {
        git commit -m "$message"
        Write-Host "Commit realizado em $branchName." -ForegroundColor Green
    } else {
        Write-Host "Nenhuma alteração pendente para $branchName (ou arquivos já incluídos em commits anteriores)." -ForegroundColor Gray
    }
}

# ---------------------------------------------------
# 1. Refatoração Core: Transações (Renomeação Payment -> Transaction)
# ---------------------------------------------------
$filesTransactions = @(
    "src/transactions/",
    "src/entities/transaction.py",
    "src/exceptions/transactions.py",
    "tests/transactions/",
    "alembic/versions/0b09e7de7ead_rename_payments_to_transactions.py",
    "alembic/versions/b525108c8152_unique_payment_open_finance_id_per_user.py",
    "alembic/versions/f7f364b5cfa6_remove_check_category_required.py",
    "src/entities/user.py",
    "src/entities/category.py",
    "src/entities/bank.py",
    "main.py",
    "src/entities/payment.py",
    "src/exceptions/payments.py",
    "src/payments/",
    "tests/payments/",
    "scripts/dump_transactions.py"
)
Create-Commit -branchName "refactor/transactions-core" -files $filesTransactions -message "refactor(core): rename payments to transactions and update core entities"

# ---------------------------------------------------
# 2. Refatoração: Merchants e Aliases
# ---------------------------------------------------
$filesMerchants = @(
    "src/entities/merchant.py",
    "src/entities/merchant_alias.py",
    "src/aliases/service.py",
    "alembic/versions/0970ee4ca956_refactor_merchant_categories_and_fix_.py",
    "alembic/versions/0c1b21122f37_o_nome_do_merchant_é_único_apenas_por_.py",
    "tests/merchants/test_alias_update_propagation.py"
)
Create-Commit -branchName "refactor/merchants" -files $filesMerchants -message "refactor(merchants): improve merchant entity and alias system"

# ---------------------------------------------------
# 3. Feature: Open Finance Update
# ---------------------------------------------------
$filesOpenFinance = @(
    "src/open_finance/",
    "src/entities/open_finance_item.py",
    "src/entities/open_finance_account.py",
    "alembic/versions/5d9d4215e9d6_create_open_finance_tables.py",
    "alembic/versions/184d41fe51e1_add_server_defaults_to_open_finance_.py",
    "src/banks/sync_service.py",
    "src/banks/controller.py",
    "src/banks/model.py",
    "src/categories/sync_service.py",
    "src/categories/controller.py",
    "src/categories/service.py",
    "tests/open_finance/",
    "PENDING_OPEN_FINANCE_UPDATE_PLAN.md",
    "src/open_finance/webhook/"
)
Create-Commit -branchName "feat/open-finance-update" -files $filesOpenFinance -message "feat(open-finance): enhance integration, sync logic and webhooks"

# ---------------------------------------------------
# 4. Feature: Auth e Admin
# ---------------------------------------------------
$filesAuth = @(
    "src/auth/",
    "tests/auth/",
    "alembic/versions/c3160de3ae62_add_is_admin_to_users.py"
)
Create-Commit -branchName "feat/auth-admin" -files $filesAuth -message "feat(auth): add admin user capability and auth improvements"

# ---------------------------------------------------
# 5. Feature: Dashboard Logic
# ---------------------------------------------------
$filesDashboard = @(
    "src/dashboard/",
    "tests/dashboard/"
)
Create-Commit -branchName "feat/dashboard-improvements" -files $filesDashboard -message "feat(dashboard): refine dashboard logic and add tests"

# ---------------------------------------------------
# 6. Chore: Manutenção e Limpeza
# ---------------------------------------------------
# Adiciona tudo que sobrou
$filesChore = @(
    "pyproject.toml",
    "uv.lock",
    "alembic/env.py",
    "src/api.py",
    "src/utils/",
    "." # Catch-all para o resto
)
Create-Commit -branchName "chore/project-maintenance" -files $filesChore -message "chore: update dependencies and project configuration"

Write-Host "`n---------------------------------------------------"
Write-Host "Reestruturação concluída!" -ForegroundColor Green
Write-Host "Branches criadas (em ordem de dependência):"
Write-Host "1. refactor/transactions-core"
Write-Host "2. refactor/merchants"
Write-Host "3. feat/open-finance-update"
Write-Host "4. feat/auth-admin"
Write-Host "5. feat/dashboard-improvements"
Write-Host "6. chore/project-maintenance"
Write-Host "---------------------------------------------------"
Write-Host "Você está agora na branch 'chore/project-maintenance' que contém TODAS as alterações aplicadas."
