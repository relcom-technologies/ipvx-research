I have prepared an explicit requirement for the written client profile: safe automatic recovery requires durable storage of the intake-account binding, messageId and complete original SendMessage params BEFORE the first send. The server cannot enforce that the client has saved them. Persist proposalId/taskId when the reply arrives; keep credentials out of shared traces.

One precision on byte equivalence: literal HTTP byte equality is not required. We parse JSON and fingerprint sorted-key canonical params, so object-key order and whitespace can differ. Rebuilding fields or configuration from mutable state is unsafe; preserve the original full params. The outer JSON-RPC id can change. We do not promise broader semantic normalization.

409 message_id_reused is a non-transient conflict for those changed params. Repeating that conflicting payload will not recover anything. It is NOT a terminal decision on the stored proposal, and does not decline, cancel or delete it. Replaying the saved original params with the original messageId recovers the saved result. A client should not drop the logical submission or automatically generate a new messageId after 409, because a fresh ID permits a second proposal.

If params were lost but proposalId remains, use get_proposal_status with a fresh messageId. If only taskId remains, GetTask can recover its stored receipt artifact, subject to authorization/retention. With neither original params nor usable receipt/task IDs, the safe client outcome is UNKNOWN: stop automatic resubmission and reconcile the account's records with the operator. ListTasks may help investigation, but there is no guaranteed recovery mapping from otherwise lost state. Do not interpret missing local state as a missing server proposal. Valid account access is still required; the current 30-day token and retention limits apply.

For a first joint test, can we narrow the pilot to two sequences?
A. Persist params, lose the accepted response, receive 409 after an accidental payload change, then replay the persisted original and recover one logical proposal/receipt.
B. Deliberately lose both params and receipt/task IDs: the client must mark the outcome unknown and stop, without creating a fresh-ID replacement automatically.

The isolated server trace would establish the actual proposal count; your independent client would establish the observed recovery behavior. We would publish mismatches and negative results. No production fault injection or resource access is needed for agreeing this protocol.

Would you take one of these independent-client cases, or prefer to review the expected client-state transitions only?
