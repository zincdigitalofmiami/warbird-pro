// eslint-disable-next-line @typescript-eslint/no-require-imports
const vscode = require('vscode');

function activate(context) {
  const disposable = vscode.commands.registerCommand('warbirdHermes.launchAcp', async () => {
    await vscode.commands.executeCommand('workbench.view.extension.acp-client');
    await vscode.commands.executeCommand('acp.openChat');
    try {
      await vscode.commands.executeCommand('acp.connectAgent', 'Hermes Agent');
    } catch (_error) {
      vscode.window.showWarningMessage(
        'ACP Client opened. If Hermes did not connect automatically, select Hermes Agent from the ACP Client Agents view.'
      );
    }
  });
  context.subscriptions.push(disposable);
}

function deactivate() {}

module.exports = { activate, deactivate };
