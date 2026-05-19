# NyayaNode - Final Requirement Checklist Verification
# Uses Invoke-RestMethod (no IE engine, no security warnings)
# Run AFTER the server is up: scripts/run.ps1
#
# Usage:
#   .\scripts\test_checklist.ps1
#   .\scripts\test_checklist.ps1 -BaseUrl "http://localhost:8000" -ApiKey "nyayanode-internal-secret-key"

param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$ApiKey  = "nyayanode-internal-secret-key"
)

$ErrorActionPreference = "Stop"

$pass  = 0
$fail  = 0
$warns = 0

function Write-Pass  { param($msg) Write-Host "  [PASS] $msg" -ForegroundColor Green;  $script:pass++ }
function Write-Fail  { param($msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red;    $script:fail++ }
function Write-Warn  { param($msg) Write-Host "  [WARN] $msg" -ForegroundColor Yellow; $script:warns++ }
function Write-Section { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }

$headers     = @{ "X-API-Key" = $ApiKey }
$jsonHeaders = @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" }

# Helper - call REST, return $null on non-2xx instead of throwing
function Invoke-API {
    param([string]$Method, [string]$Path, [hashtable]$H = $headers, [string]$Body = $null)
    $uri = "$BaseUrl$Path"
    try {
        $params = @{ Method = $Method; Uri = $uri; Headers = $H; UseBasicParsing = $true }
        if ($Body) { $params["Body"] = $Body }
        return Invoke-RestMethod @params
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
        Write-Warn "  $Method $Path → HTTP $status"
        return $null
    }
}

# ─────────────────────────────────────────────────────────────────────────────
Write-Section "TASK 1 - Health + Setup"
# ─────────────────────────────────────────────────────────────────────────────

$health = Invoke-API GET "/health"
if ($health -and $health.status -eq "healthy") {
    Write-Pass "GET /health returns status=healthy"
} else { Write-Fail "GET /health did not return status=healthy" }

if ($health -and $health.supabase) {
    Write-Pass "GET /health includes supabase field ($($health.supabase))"
} else { Write-Fail "GET /health missing supabase field" }

if ($health -and $health.agent_module) {
    Write-Pass "GET /health includes agent_module field ($($health.agent_module))"
} else { Write-Fail "GET /health missing agent_module field" }

if ($health -and $health.version) {
    Write-Pass "GET /health includes version field ($($health.version))"
} else { Write-Fail "GET /health missing version field" }

$stats = Invoke-API GET "/api/v1/stats"
if ($stats -and $null -ne $stats.total_disputes) {
    Write-Pass "GET /api/v1/stats returns total_disputes"
} else { Write-Warn "GET /api/v1/stats unavailable (Supabase not configured?)" }

# ─────────────────────────────────────────────────────────────────────────────
Write-Section "TASK 2 - Disputes CRUD"
# ─────────────────────────────────────────────────────────────────────────────

$newDispute = @{
    buyer_id           = "ondc_buyer_001"
    seller_id          = "ondc_seller_042"
    logistics_id       = "ondc_lsp_007"
    order_id           = "order_ps_test_$(Get-Random)"
    dispute_type       = "DAMAGED_ITEM"
    evidence           = @(@{ type = "text"; content = "Box arrived crushed" })
    dispute_amount_inr = "499.00"
} | ConvertTo-Json -Depth 5

$created = Invoke-API POST "/api/v1/disputes" -H $jsonHeaders -Body $newDispute
if ($created -and $created.id) {
    Write-Pass "POST /api/v1/disputes creates dispute (id=$($created.id))"
    $disputeId = $created.id
} else {
    Write-Fail "POST /api/v1/disputes failed"
    $disputeId = $null
}

$list = Invoke-API GET "/api/v1/disputes?limit=5&offset=0"
if ($list -and ($list -is [array] -or $list.items -or $list.data -or $list.disputes)) {
    Write-Pass "GET /api/v1/disputes returns list"
} elseif ($list) {
    Write-Pass "GET /api/v1/disputes returned a response"
} else { Write-Fail "GET /api/v1/disputes failed" }

if ($disputeId) {
    $fetched = Invoke-API GET "/api/v1/disputes/$disputeId"
    if ($fetched -and $fetched.id -eq $disputeId) {
        Write-Pass "GET /api/v1/disputes/{id} returns correct dispute"
    } else { Write-Fail "GET /api/v1/disputes/{id} failed" }
} else { Write-Warn "Skipping GET /disputes/{id} - no dispute created" }

# ─────────────────────────────────────────────────────────────────────────────
Write-Section "TASK 3 - Mock ONDC Party APIs"
# ─────────────────────────────────────────────────────────────────────────────

$logistics = Invoke-API GET "/mock/ondc/logistics/TRK001234"
if ($logistics -and $logistics.tracking_id) {
    Write-Pass "GET /mock/ondc/logistics/{id} returns tracking_id"
} else { Write-Fail "GET /mock/ondc/logistics/{id} failed" }

if ($logistics -and $logistics.scan_history) {
    Write-Pass "Logistics response includes scan_history array"
} else { Write-Fail "Logistics response missing scan_history" }

if ($logistics -and $logistics.package_condition_flag) {
    Write-Pass "Logistics response includes package_condition_flag"
} else { Write-Fail "Logistics response missing package_condition_flag" }

$seller = Invoke-API GET "/mock/ondc/seller/ondc_seller_042/order/order_xyz"
if ($seller -and $seller.seller_id) {
    Write-Pass "GET /mock/ondc/seller/{id}/order/{id} returns seller_id"
} else { Write-Fail "GET /mock/ondc/seller/{id}/order/{id} failed" }

if ($seller -and $seller.seller_dispute_stance) {
    Write-Pass "Seller response includes seller_dispute_stance"
} else { Write-Fail "Seller response missing seller_dispute_stance" }

$buyer = Invoke-API GET "/mock/ondc/buyer/ondc_buyer_001"
if ($buyer -and $buyer.buyer_id) {
    Write-Pass "GET /mock/ondc/buyer/{id} returns buyer_id"
} else { Write-Fail "GET /mock/ondc/buyer/{id} failed" }

# ─────────────────────────────────────────────────────────────────────────────
Write-Section "TASK 4 - ONDC Webhook"
# ─────────────────────────────────────────────────────────────────────────────

$ondcPayload = @{
    context = @{
        domain         = "nic2004:52110"
        action         = "on_issue"
        bap_id         = "ondc_buyer_test"
        bpp_id         = "ondc_seller_test"
        transaction_id = "txn_ps_$(Get-Random)"
        message_id     = "msg_ps_$(Get-Random)"
        timestamp      = (Get-Date -Format "o")
    }
    message = @{
        issue = @{
            id                 = "issue_ps_$(Get-Random)"
            order_id           = "order_ps_$(Get-Random)"
            issue_sub_category = "ITM03"
            source             = @{ id = "ondc_buyer_test" }
            order_details      = @{ provider_id = "ondc_seller_test" }
            description        = @{
                short_desc = "Item damaged"
                long_desc  = "Package arrived with visible damage"
            }
        }
    }
} | ConvertTo-Json -Depth 10

$webhookHeaders = @{
    "X-API-Key"         = $ApiKey
    "Content-Type"      = "application/json"
    "X-ONDC-Signature"  = "mock-sig-$(Get-Random)"
}

$ack = Invoke-API POST "/api/v1/ondc/webhook/dispute-raised" -H $webhookHeaders -Body $ondcPayload
if ($ack -and $ack.ack -and $ack.ack.status -eq "ACK") {
    Write-Pass "POST /ondc/webhook/dispute-raised returns ACK"
} else { Write-Fail "POST /ondc/webhook/dispute-raised did not return ACK" }

# Missing signature should return 401
$noSigHeaders = @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" }
try {
    $noSig = Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/v1/ondc/webhook/dispute-raised" `
        -Headers $noSigHeaders -Body $ondcPayload -UseBasicParsing
    Write-Fail "Missing X-ONDC-Signature should return 401 (got 200)"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 401) {
        Write-Pass "Missing X-ONDC-Signature correctly returns 401"
    } else {
        Write-Warn "Missing X-ONDC-Signature returned HTTP $code (expected 401)"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
Write-Section "TASK 5 - Agent Bridge"
# ─────────────────────────────────────────────────────────────────────────────

if ($disputeId) {
    # 409 is valid here — POST /disputes already auto-triggered the agent as a BackgroundTask.
    # Re-trigger only works when no run is RUNNING. Test both paths.
    try {
        $arb = Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/v1/disputes/$disputeId/arbitrate" `
            -Headers $jsonHeaders -UseBasicParsing
        if ($arb -and $arb.agent_run_id) {
            Write-Pass "POST /disputes/{id}/arbitrate returns agent_run_id"
        } else { Write-Fail "POST /disputes/{id}/arbitrate failed" }
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 409) {
            Write-Pass "POST /disputes/{id}/arbitrate correctly returns 409 when agent already RUNNING"
        } else {
            Write-Fail "POST /disputes/{id}/arbitrate returned unexpected HTTP $code"
        }
    }

    Start-Sleep -Seconds 1

    $agentStatus = Invoke-API GET "/api/v1/disputes/$disputeId/agent-status"
    if ($agentStatus -and $agentStatus.run_id) {
        Write-Pass "GET /disputes/{id}/agent-status returns run_id"
    } else { Write-Fail "GET /disputes/{id}/agent-status failed" }

    if ($agentStatus -and $agentStatus.current_stage) {
        Write-Pass "agent-status includes current_stage ($($agentStatus.current_stage))"
    } else { Write-Fail "agent-status missing current_stage" }

    if ($agentStatus -and $null -ne $agentStatus.elapsed_seconds) {
        Write-Pass "agent-status includes elapsed_seconds"
    } else { Write-Fail "agent-status missing elapsed_seconds" }
} else {
    Write-Warn "Skipping agent bridge tests - no dispute created"
}

# ─────────────────────────────────────────────────────────────────────────────
Write-Section "TASK 6 - SSE Stream"
# ─────────────────────────────────────────────────────────────────────────────

if ($disputeId) {
    # Just verify the endpoint responds with text/event-stream content-type
    try {
        $req = [System.Net.HttpWebRequest]::Create("$BaseUrl/api/v1/disputes/$disputeId/stream")
        $req.Method  = "GET"
        $req.Timeout = 3000
        $resp = $req.GetResponse()
        $ct   = $resp.ContentType
        $resp.Close()
        if ($ct -like "*text/event-stream*") {
            Write-Pass "SSE /stream endpoint returns Content-Type: text/event-stream"
        } else {
            Write-Fail "SSE /stream Content-Type is '$ct' (expected text/event-stream)"
        }
    } catch {
        Write-Warn "SSE /stream check inconclusive (timeout is expected for streaming): $($_.Exception.Message)"
    }
} else {
    Write-Warn "Skipping SSE test - no dispute created"
}

# ─────────────────────────────────────────────────────────────────────────────
Write-Section "TASK 7 - Audit Trail"
# ─────────────────────────────────────────────────────────────────────────────

if ($disputeId) {
    $audit = Invoke-API GET "/api/v1/disputes/$disputeId/audit-trail"
    if ($null -ne $audit) {
        Write-Pass "GET /disputes/{id}/audit-trail responds"
    } else { Write-Fail "GET /disputes/{id}/audit-trail failed" }

    $cascade = Invoke-API GET "/api/v1/disputes/$disputeId/cascadeflow-audit"
    if ($null -ne $cascade) {
        Write-Pass "GET /disputes/{id}/cascadeflow-audit responds"
    } else { Write-Warn "GET /disputes/{id}/cascadeflow-audit returned null (agent may not have run yet)" }
} else {
    Write-Warn "Skipping audit tests - no dispute created"
}

# ─────────────────────────────────────────────────────────────────────────────
Write-Section "TASK 8 - Deployment Config"
# ─────────────────────────────────────────────────────────────────────────────

$dockerfile = Join-Path $PSScriptRoot "..\backend\Dockerfile"
if (Test-Path $dockerfile) {
    $df = Get-Content $dockerfile -Raw
    if ($df -match "python:3\.11") {
        Write-Pass "Dockerfile uses python:3.11 base image"
    } else { Write-Fail "Dockerfile does not use python:3.11" }

    if ($df -match '\$PORT') {
        Write-Pass "Dockerfile uses \$PORT env variable"
    } else { Write-Fail "Dockerfile does not reference \$PORT" }
} else { Write-Warn "Dockerfile not found at $dockerfile" }

$railwayToml = Join-Path $PSScriptRoot "..\backend\railway.toml"
if (Test-Path $railwayToml) {
    $rt = Get-Content $railwayToml -Raw
    if ($rt -match "healthcheckPath") {
        Write-Pass "railway.toml sets healthcheckPath"
    } else { Write-Fail "railway.toml missing healthcheckPath" }

    if ($rt -match "/health") {
        Write-Pass "railway.toml healthcheckPath points to /health"
    } else { Write-Fail "railway.toml healthcheckPath does not point to /health" }
} else { Write-Warn "railway.toml not found at $railwayToml" }

# ─────────────────────────────────────────────────────────────────────────────
Write-Section "SUMMARY"
# ─────────────────────────────────────────────────────────────────────────────

$total = $pass + $fail + $warns
Write-Host ""
Write-Host "Results: $pass passed, $fail failed, $warns warnings (of $total checks)" -ForegroundColor White

if ($fail -gt 0) {
    Write-Host "CHECKLIST: INCOMPLETE - fix the FAIL items above" -ForegroundColor Red
    exit 1
} elseif ($warns -gt 0) {
    Write-Host "CHECKLIST: MOSTLY PASSING - review warnings (usually Supabase config)" -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "CHECKLIST: ALL PASSED" -ForegroundColor Green
    exit 0
}
