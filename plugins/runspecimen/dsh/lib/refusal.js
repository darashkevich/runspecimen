/**
 * The human gate.
 *
 * RunSpecimen's whole value proposition is that a consequential run is bound to
 * a human decision made locally. Three commands carry that decision:
 *
 *   approve         — types APPROVE on a real TTY, binding contract to source
 *   remote-confirm  — arms/refuses a Mac-armed confirmation for a phone holder
 *   abandon         — marks a crashed run failed after TTY confirmation
 *
 * A plugin that could perform any of them would move the decision into the
 * agent's own process, where the agent can both propose and consent. This module
 * makes that refusal explicit and explainable rather than a silent absence.
 *
 * @module runspecimen-dsh-plugin/refusal
 */

/** Actions refused to the agent, with the human-only reason. */
export const REFUSED_ACTIONS = Object.freeze(["approve", "remote_confirm", "abandon"]);

const REASONS = Object.freeze({
  approve:
    "approval must be typed by a human at a real terminal: run `runspecimen approve --workspace <ws> --contract <contract.json>` yourself and type APPROVE. No plugin, MCP adapter or companion app can approve, and there is no approval token to hand to an agent.",
  remote_confirm:
    "remote settlement is a holder decision on a paired device. Arm it with `runspecimen remote-confirm arm` and let the holder confirm or refuse; an agent must not settle on the holder's behalf.",
  abandon:
    "abandoning a crashed run needs TTY confirmation because it marks the run failed. Run `runspecimen abandon --workspace <ws> --campaign-id <id> --run-id <id>` yourself.",
});

/**
 * Explain why one action is refused and what the human should run instead.
 *
 * @param action - one of REFUSED_ACTIONS.
 * @returns a message naming the reason and the human command.
 */
export function refusalMessage(action) {
  const reason = REASONS[action];
  if (reason === undefined) {
    throw new Error(`'${String(action)}' is not a human-gate action known to this plugin`);
  }
  return `RunSpecimen refused '${action}' to the agent because ${reason}`;
}
