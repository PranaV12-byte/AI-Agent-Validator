"""
Safebot Audit Log - Algorand ARC-4 Smart Contract
Deployed via AlgoKit. Provides three methods:
1. register_policy(policy_id, policy_hash) - immutable policy registry
2. log_violation(audit_id, violation_type, payload_hash) - tamper-proof violation log
3. log_approval(audit_id, payload_hash) - tamper-proof approval log
"""

from algopy import ARC4Contract, Bytes, String, arc4, log


class SafebotAuditLog(ARC4Contract):
    @arc4.abimethod()
    def register_policy(self, policy_id: Bytes, policy_hash: Bytes) -> String:
        log(b"POLICY_REGISTERED")
        log(policy_id)
        log(policy_hash)
        return String("ok")

    @arc4.abimethod()
    def log_violation(
        self,
        audit_id: Bytes,
        violation_type: Bytes,
        payload_hash: Bytes,
    ) -> String:
        log(b"VIOLATION")
        log(audit_id)
        log(violation_type)
        log(payload_hash)
        return String("ok")

    @arc4.abimethod()
    def log_approval(self, audit_id: Bytes, payload_hash: Bytes) -> String:
        log(b"APPROVAL")
        log(audit_id)
        log(payload_hash)
        return String("ok")
