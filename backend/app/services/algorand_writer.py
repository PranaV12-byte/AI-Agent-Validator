"""
Algorand Interaction Service.
Submits audit events and policy registrations to the SafebotAuditLog smart contract.
IMPORTANT: For MVP/hackathon, if Algorand is not configured (app_id=0),
this gracefully returns a mock TX ID and logs a warning.
"""

import structlog
from algosdk import mnemonic
from algosdk.transaction import ApplicationCallTxn, wait_for_confirmation
from algosdk.v2client import algod

from app.config import settings

logger = structlog.get_logger()

ALGOD_ADDRESS = "https://testnet-api.4160.nodely.dev"
ALGOD_TOKEN = ""

METHOD_LOG_VIOLATION = b"log_violation"
METHOD_LOG_APPROVAL = b"log_approval"
METHOD_REGISTER_POLICY = b"register_policy"


def _get_client() -> algod.AlgodClient:
    return algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)


def _get_sender_info() -> tuple[str, str]:
    """Return (address, private_key) from mnemonic."""
    if not settings.algorand_mnemonic or settings.algorand_mnemonic == "CHANGE-ME":
        raise ValueError("Algorand mnemonic not configured")
    private_key = mnemonic.to_private_key(settings.algorand_mnemonic)
    address = mnemonic.to_public_key(settings.algorand_mnemonic)
    return address, private_key


def submit_audit_to_algorand(
    audit_log_id: str,
    action: str,
    violation_type: str,
    payload_hash: str,
) -> str:
    """Submit a violation or approval log to the Algorand smart contract."""
    if settings.algorand_app_id == 0:
        logger.warning(
            "algorand_not_configured", msg="Skipping chain submission (app_id=0)"
        )
        return f"mock_tx_{audit_log_id[:8]}"

    client = _get_client()
    address, private_key = _get_sender_info()
    params = client.suggested_params()
    method = METHOD_LOG_VIOLATION if action == "BLOCKED" else METHOD_LOG_APPROVAL

    txn = ApplicationCallTxn(
        sender=address,
        sp=params,
        index=settings.algorand_app_id,
        app_args=[
            method,
            audit_log_id.encode(),
            violation_type.encode() if violation_type else b"none",
            bytes.fromhex(payload_hash),
        ],
    )

    signed_txn = txn.sign(private_key)
    tx_id = client.send_transaction(signed_txn)
    wait_for_confirmation(client, tx_id, 4)

    logger.info(
        "algorand_tx_submitted", tx_id=tx_id, action=action, audit_id=audit_log_id
    )
    return tx_id


def register_policy_on_algorand(policy_id: str, policy_hash: str) -> str:
    """Register a policy hash on-chain for tamper-proof verification."""
    if settings.algorand_app_id == 0:
        logger.warning(
            "algorand_not_configured", msg="Skipping policy registration (app_id=0)"
        )
        return f"mock_tx_policy_{policy_id[:8]}"

    client = _get_client()
    address, private_key = _get_sender_info()
    params = client.suggested_params()

    txn = ApplicationCallTxn(
        sender=address,
        sp=params,
        index=settings.algorand_app_id,
        app_args=[
            METHOD_REGISTER_POLICY,
            policy_id.encode(),
            bytes.fromhex(policy_hash),
        ],
    )

    signed_txn = txn.sign(private_key)
    tx_id = client.send_transaction(signed_txn)
    wait_for_confirmation(client, tx_id, 4)

    logger.info("algorand_policy_registered", tx_id=tx_id, policy_id=policy_id)
    return tx_id
