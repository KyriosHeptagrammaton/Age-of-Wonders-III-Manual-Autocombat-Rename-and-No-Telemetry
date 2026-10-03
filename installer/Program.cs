using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;

namespace AoW3Mod
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("patches.json"))
                using (var reader = new StreamReader(stream))
                    Application.Run(new MainWindow(Data.Json().Deserialize<Manifest>(reader.ReadToEnd())));
            }
            catch (Exception error)
            {
                MessageBox.Show(error.Message, "AoW3 mod installer", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
    sealed class MainWindow : Form
    {
        readonly Manifest manifest;
        readonly TextBox folder = new TextBox { Dock = DockStyle.Fill };
        readonly TextBox output = new TextBox { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical,
            Dock = DockStyle.Fill, BackColor = Color.White, BorderStyle = BorderStyle.FixedSingle };
        readonly Button browse = new Button { Text = "Browse...", AutoSize = true };
        readonly Button check = new Button { Text = "Check Files", AutoSize = true };
        readonly Button install = new Button { Text = "Install Mod", AutoSize = true };
        readonly Button restore = new Button { Text = "Restore Originals", AutoSize = true };
        bool busy;
        public MainWindow(Manifest patch)
        {
            manifest = patch;
            Text = "Age of Wonders III — Community Mod " + patch.Version;
            Font = new Font("Segoe UI", 10F);
            ClientSize = new Size(740, 515);
            MinimumSize = new Size(680, 490);
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Dpi;
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(22), ColumnCount = 1, RowCount = 6 };
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 90));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 45));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            layout.Controls.Add(new Label { Text = "Manual autocombat & unit renaming", Font = new Font("Segoe UI", 17F, FontStyle.Bold), Dock = DockStyle.Fill });
            layout.Controls.Add(new Label { Text = "Preview autocombat results, accept or fight manually with the same seed.\r\nClick unit names to rename them. Built-in game telemetry is disabled.\r\n\r\nInstalls both modes. Includes the preview HP tooltip fix.", Dock = DockStyle.Fill });
            layout.Controls.Add(new Label { Text = "Game folder (containing AoW3.exe and AoW3_Debug.exe)", Dock = DockStyle.Fill });
            var selection = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2 };
            selection.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            selection.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 100));
            selection.Controls.Add(folder, 0, 0);
            selection.Controls.Add(browse, 1, 0);
            layout.Controls.Add(selection);
            var actions = new FlowLayoutPanel { Dock = DockStyle.Fill };
            actions.Controls.AddRange(new Control[] { check, install, restore });
            layout.Controls.Add(actions);
            layout.Controls.Add(output);
            Controls.Add(layout);
            string here = AppDomain.CurrentDomain.BaseDirectory;
            if (File.Exists(Path.Combine(here, "AoW3_Debug.exe"))) folder.Text = here;
            output.Text = "Close the game and launcher, select the installation folder, then click Check Files or Install Mod.\r\n\r\nOriginal files are backed up in AoW3ModBackup. The installer refuses unknown builds or conflicting UI changes.\r\n\r\nExisting manual installation? Keep your original backups. Restore those originals before installing if you want this installer to manage uninstalling.";
            browse.Click += delegate
            {
                using (var dialog = new FolderBrowserDialog { Description = "Select the Age of Wonders III installation folder", ShowNewFolderButton = false })
                {
                    if (Directory.Exists(folder.Text)) dialog.SelectedPath = folder.Text;
                    if (dialog.ShowDialog(this) == DialogResult.OK) folder.Text = dialog.SelectedPath;
                }
            };
            check.Click += delegate { Run(0); };
            install.Click += delegate { Run(1); };
            restore.Click += delegate { Run(2); };
            FormClosing += delegate(object sender, FormClosingEventArgs e) { if (busy) e.Cancel = true; };
        }
        static void CheckProcesses()
        {
            foreach (var process in Process.GetProcesses())
                using (process)
                {
                    string name;
                    try { name = process.ProcessName; }
                    catch (InvalidOperationException) { continue; }
                    if (new[] { "AoW3", "AoW3_Debug", "AoW3Launcher" }.Contains(name, StringComparer.OrdinalIgnoreCase))
                        throw new IOException("Close Age of Wonders III and its launcher before installing or restoring.");
                }
        }
        void Run(int action)
        {
            string selected = folder.Text.Trim();
            if (selected.Length == 0) { output.Text = "Select the game folder first."; return; }
            busy = true;
            folder.Enabled = browse.Enabled = check.Enabled = install.Enabled = restore.Enabled = false;
            output.Text = action == 0 ? "Checking files..." : action == 1 ? "Verifying, backing up and installing..." : "Verifying backups and restoring...";
            var worker = new BackgroundWorker();
            worker.DoWork += delegate(object sender, DoWorkEventArgs args)
            {
                if (action != 0) CheckProcesses();
                var engine = new Installer(selected, manifest);
                args.Result = action == 0 ? engine.Check() : action == 1 ? engine.Install() : engine.Uninstall();
            };
            worker.RunWorkerCompleted += delegate(object sender, RunWorkerCompletedEventArgs args)
            {
                busy = false;
                folder.Enabled = browse.Enabled = check.Enabled = install.Enabled = restore.Enabled = true;
                output.Text = args.Error == null ? (string)args.Result : args.Error.Message;
                if (args.Error is UnauthorizedAccessException)
                    output.Text += "\r\n\r\nWindows denied write access. Close this installer and run it as administrator, then select the same game folder.";
                worker.Dispose();
            };
            worker.RunWorkerAsync();
        }
    }
}
