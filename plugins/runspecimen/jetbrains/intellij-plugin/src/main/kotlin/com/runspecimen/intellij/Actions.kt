package com.runspecimen.intellij

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Shared helpers for RunSpecimen IDE actions.
 *
 * Approval is never executed here — [RequestApprovalAction] only displays the
 * human TTY command. Lifecycle actions shell out to ide_actions.py / adapter.
 */
internal object RunSpecimenCli {
    private val forbidden = setOf("approve", "remote-confirm")

    fun pluginRoot(): File? {
        val fromProp = System.getProperty("runspecimen.plugin.root")
        if (!fromProp.isNullOrBlank()) {
            return File(fromProp)
        }
        // Prefer sibling checkout layout: .../plugins/runspecimen/jetbrains/intellij-plugin
        val cwd = File(System.getProperty("user.dir") ?: ".")
        val candidate = cwd.resolve("../scripts/ide_actions.py").normalize()
        if (candidate.isFile) {
            return candidate.parentFile.parentFile
        }
        return null
    }

    fun ideActionsScript(): File? {
        val root = pluginRoot() ?: return null
        val script = File(root, "scripts/ide_actions.py")
        return script.takeIf { it.isFile }
    }

    fun runAction(
        project: Project?,
        action: String,
        workspace: String?,
        contract: String?,
        campaignId: String? = null,
        runId: String? = null,
    ): String {
        require(action !in forbidden) { "Action '$action' is forbidden in the IDE adapter" }
        val script = ideActionsScript()
            ?: return "ide_actions.py not found. Set -Drunspecimen.plugin.root=.../jetbrains or install from the repo checkout."
        val cmd = mutableListOf("python3", script.absolutePath, action)
        if (!workspace.isNullOrBlank()) {
            cmd += listOf("--workspace", workspace)
        }
        if (!contract.isNullOrBlank()) {
            cmd += listOf("--contract", contract)
        }
        if (!campaignId.isNullOrBlank()) {
            cmd += listOf("--campaign-id", campaignId)
        }
        if (!runId.isNullOrBlank()) {
            cmd += listOf("--run-id", runId)
        }
        val process = ProcessBuilder(cmd)
            .directory(project?.basePath?.let { File(it) })
            .redirectErrorStream(true)
            .start()
        val finished = process.waitFor(120, TimeUnit.SECONDS)
        val output = process.inputStream.bufferedReader().readText()
        if (!finished) {
            process.destroyForcibly()
            return "Timed out running RunSpecimen action '$action'."
        }
        return if (output.isBlank()) {
            "exit_code=${process.exitValue()}"
        } else {
            output
        }
    }

    fun promptPaths(project: Project?, title: String): Pair<String, String>? {
        val base = project?.basePath ?: System.getProperty("user.home")
        val workspace = Messages.showInputDialog(
            project,
            "Workspace path:",
            title,
            Messages.getQuestionIcon(),
            base,
            null,
        ) ?: return null
        val contract = Messages.showInputDialog(
            project,
            "Contract JSON path:",
            title,
            Messages.getQuestionIcon(),
            "",
            null,
        ) ?: return null
        return workspace to contract
    }
}

class ValidateAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val paths = RunSpecimenCli.promptPaths(e.project, "RunSpecimen Validate") ?: return
        val out = RunSpecimenCli.runAction(e.project, "validate", paths.first, paths.second)
        Messages.showInfoMessage(e.project, out, "RunSpecimen Validate")
    }
}

class StatusAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project
        val base = project?.basePath ?: System.getProperty("user.home")
        val workspace = Messages.showInputDialog(project, "Workspace:", "RunSpecimen Status", null, base, null)
            ?: return
        val campaign = Messages.showInputDialog(project, "Campaign ID:", "RunSpecimen Status", null, "", null)
            ?: return
        val runId = Messages.showInputDialog(project, "Run ID:", "RunSpecimen Status", null, "", null)
            ?: return
        val out = RunSpecimenCli.runAction(
            project,
            "status",
            workspace,
            null,
            campaignId = campaign,
            runId = runId,
        )
        Messages.showInfoMessage(project, out, "RunSpecimen Status")
    }
}

class RequestApprovalAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val paths = RunSpecimenCli.promptPaths(e.project, "RunSpecimen Request Approval") ?: return
        // Never executes approve — only prints the human handoff text.
        val out = RunSpecimenCli.runAction(e.project, "request-approval", paths.first, paths.second)
        Messages.showInfoMessage(
            e.project,
            out + "\n\nThis IDE action never types APPROVE or runs `runspecimen approve`.",
            "Human TTY Approval Required",
        )
    }
}

class VerifyAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val paths = RunSpecimenCli.promptPaths(e.project, "RunSpecimen Verify") ?: return
        val campaign = Messages.showInputDialog(e.project, "Campaign ID:", "RunSpecimen Verify", null, "", null)
            ?: return
        val runId = Messages.showInputDialog(e.project, "Run ID:", "RunSpecimen Verify", null, "", null)
            ?: return
        val out = RunSpecimenCli.runAction(
            e.project,
            "verify",
            paths.first,
            paths.second,
            campaignId = campaign,
            runId = runId,
        )
        Messages.showInfoMessage(e.project, out, "RunSpecimen Verify")
    }
}
