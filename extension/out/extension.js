"use strict";
/**
 * CoWorkX VS Code Extension
 *
 * Command "CoWorkX: Fix Bugs in This File":
 *   1. Reads the active file's content
 *   2. POSTs a task to the coordinator (machine auto-selected server-side)
 *   3. Opens an Output channel and polls GET /tasks/{id} every 3s
 *   4. Prints each new agent step, then the final result on completion
 *
 * Uses Node's global fetch (VS Code 1.85+ runs Node 18+), so no dependencies.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
let channel;
function activate(context) {
    channel = vscode.window.createOutputChannel('CoWorkX');
    const disposable = vscode.commands.registerCommand('coworkx.fixBugs', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showErrorMessage('CoWorkX: Open a file first.');
            return;
        }
        const coordinatorUrl = vscode.workspace
            .getConfiguration('coworkx')
            .get('coordinatorUrl', 'http://localhost:8000');
        const fileName = editor.document.fileName.split(/[\\/]/).pop() || 'file';
        const code = editor.document.getText();
        channel.show(true);
        channel.appendLine('────────────────────────────────────────');
        channel.appendLine(`CoWorkX: Submitting "${fileName}" to the AI workforce…`);
        const taskDescription = `Fix all bugs in this code and explain the fixes. File: ${fileName}\n\n${code}`;
        let taskId;
        try {
            const res = await fetch(`${coordinatorUrl}/tasks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_description: taskDescription, task_type: 'coding' }),
            });
            const data = await res.json();
            if (!res.ok) {
                channel.appendLine(`CoWorkX: ❌ Submit failed: ${data.detail || res.status}`);
                vscode.window.showErrorMessage(`CoWorkX: ${data.detail || 'Submit failed'}`);
                return;
            }
            taskId = data.id;
        }
        catch (e) {
            channel.appendLine(`CoWorkX: ❌ Network error — is the coordinator running? (${e.message})`);
            vscode.window.showErrorMessage('CoWorkX: Could not reach the coordinator.');
            return;
        }
        channel.appendLine(`CoWorkX: Task submitted (ID: ${taskId})`);
        vscode.window.showInformationMessage(`CoWorkX: Task submitted (${taskId.slice(0, 8)}…)`);
        await pollTask(coordinatorUrl, taskId);
    });
    context.subscriptions.push(disposable);
}
async function pollTask(coordinatorUrl, taskId) {
    let lastStep = 0;
    const maxPolls = 80; // ~4 minutes at 3s
    for (let i = 0; i < maxPolls; i++) {
        await sleep(3000);
        let task;
        try {
            const res = await fetch(`${coordinatorUrl}/tasks/${taskId}`);
            task = await res.json();
        }
        catch {
            continue; // transient — keep polling
        }
        const steps = task.steps || [];
        for (const step of steps) {
            if (step.step_number > lastStep) {
                lastStep = step.step_number;
                const reason = step.reasoning ? ` — ${step.reasoning}` : '';
                channel.appendLine(`CoWorkX: Agent step ${step.step_number} — ${step.action_type}${reason}`);
            }
        }
        if (task.status === 'completed') {
            channel.appendLine('CoWorkX: ✅ Complete! Result:');
            channel.appendLine(task.output_url || '(no output)');
            vscode.window.showInformationMessage('CoWorkX: Task complete! ✅');
            return;
        }
        if (task.status === 'failed') {
            channel.appendLine(`CoWorkX: ❌ Task failed: ${task.error_message || 'unknown error'}`);
            vscode.window.showErrorMessage('CoWorkX: Task failed.');
            return;
        }
    }
    channel.appendLine('CoWorkX: ⏱ Stopped polling (timeout). Check the web dashboard for status.');
}
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
function deactivate() { }
//# sourceMappingURL=extension.js.map