using System;
using System.IO;
using System.Linq;
using System.Text;
using AoW3Mod;

sealed class Fixture
{
    public Manifest Patch { get; set; }
    public string[] Originals { get; set; }
    public string[] Targets { get; set; }
}
sealed class Sandbox : IDisposable
{
    public readonly string Root = Path.Combine(Path.GetTempPath(), "aow3-installer-tests-" + Guid.NewGuid().ToString("N"));
    public readonly Fixture F;
    public Installer Engine { get { return new Installer(Root, F.Patch); } }
    public Sandbox(string json)
    {
        F = Data.Json().Deserialize<Fixture>(json);
        Directory.CreateDirectory(Root);
        for (int i = 0; i < F.Patch.Files.Length; i++)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath(i)));
            File.WriteAllBytes(FilePath(i), Convert.FromBase64String(F.Originals[i]));
        }
        File.WriteAllText(Path.Combine(Root, "unrelated-mod.txt"), "another mod");
    }
    public string FilePath(int i) { return Path.Combine(Root, F.Patch.Files[i].Path.Replace('/', Path.DirectorySeparatorChar)); }
    public string Backup(int i) { return Path.Combine(Root, Installer.BackupFolder, "original-" + i + ".bak"); }
    public string State { get { return Path.Combine(Root, Installer.BackupFolder, "state.json"); } }
    public void Originals()
    {
        for (int i = 0; i < F.Patch.Files.Length; i++)
            Tests.Assert(File.ReadAllBytes(FilePath(i)).SequenceEqual(Convert.FromBase64String(F.Originals[i])), "Exact original " + i);
    }
    public void Patched()
    {
        for (int i = 0; i < F.Patch.Files.Length; i++)
            Tests.Assert(Data.Hash(Data.Canonical(File.ReadAllBytes(FilePath(i)), F.Patch.Files[i].Encoding)) == F.Patch.Files[i].TargetSha256, "Patched target " + i);
    }
    public void Unrelated()
    {
        Tests.Assert(File.ReadAllText(Path.Combine(Root, "unrelated-mod.txt")) == "another mod", "Unrelated mod preserved");
    }
    public void Dispose() { Directory.Delete(Root, true); }
}
static class Tests
{
    static int passed;
    static int failed;
    public static void Assert(bool condition, string message) { if (!condition) throw new Exception(message); }
    static void Reject(Action action)
    {
        bool threw = false;
        try { action(); } catch (InvalidDataException) { threw = true; } catch (IOException) { threw = true; }
        Assert(threw, "Operation should have refused");
    }
    static void Test(string name, Action action)
    {
        try { action(); passed++; Console.WriteLine("PASS " + name); }
        catch (Exception error) { failed++; Console.WriteLine("FAIL " + name + ": " + error); }
    }
    static void With(string json, Action<Sandbox> action) { using (var s = new Sandbox(json)) action(s); }
    static int Main(string[] args)
    {
        string fixture = File.ReadAllText(args[0]);
        Test("Python zlib decode, copy/insert and .NET encode", () => With(fixture, s =>
        {
            for (int i = 0; i < s.F.Patch.Files.Length; i++)
            {
                var file = s.F.Patch.Files[i];
                byte[] result = Data.Apply(file, Convert.FromBase64String(s.F.Originals[i]));
                Assert(Data.Canonical(result, file.Encoding).SequenceEqual(Data.Canonical(Convert.FromBase64String(s.F.Targets[i]), file.Encoding)), "Golden target mismatch");
                if (file.Encoding == "swf") Assert(result[0] == 67, "SWF remains compressed");
            }
        }));
        Test("Install, idempotence, exact uninstall, reinstall", () => With(fixture, s =>
        {
            Assert(s.Engine.Check().Contains("Ready"), "Ready");
            s.Engine.Install(); s.Patched(); s.Unrelated();
            byte[][] backups = Enumerable.Range(0, s.F.Patch.Files.Length).Select(i => File.ReadAllBytes(s.Backup(i))).ToArray();
            s.Engine.Install();
            for (int i = 0; i < s.F.Patch.Files.Length; i++) Assert(backups[i].SequenceEqual(File.ReadAllBytes(s.Backup(i))), "Backup unchanged");
            s.Engine.Uninstall(); s.Originals(); s.Unrelated();
            s.Engine.Uninstall(); s.Originals();
            s.Engine.Install(); s.Patched();
        }));
        Test("Unknown normal executable leaves all earlier files untouched", () => With(fixture, s =>
        {
            byte[] wrong = File.ReadAllBytes(s.FilePath(4)); wrong[0] = 90; File.WriteAllBytes(s.FilePath(4), wrong);
            byte[][] before = Enumerable.Range(0, s.F.Patch.Files.Length).Select(i => File.ReadAllBytes(s.FilePath(i))).ToArray();
            Reject(() => s.Engine.Install());
            for (int i = 0; i < s.F.Patch.Files.Length; i++) Assert(before[i].SequenceEqual(File.ReadAllBytes(s.FilePath(i))), "Unknown version changed files");
            Assert(!File.Exists(s.State), "No transaction started");
        }));
        foreach (int failureIndex in new[] { 0, 2, 4 })
        {
            int index = failureIndex;
            Test("Write failure after file " + index + " rolls back", () => With(fixture, s =>
            {
                var engine = s.Engine;
                engine.AfterReplace = i => { if (i == index) throw new IOException("Injected write failure"); };
                Reject(() => engine.Install()); s.Originals(); s.Unrelated();
                s.Engine.Install(); s.Patched();
            }));
        }
        Test("Interrupted partial installation recovers", () => With(fixture, s =>
        {
            s.Engine.Install();
            File.Copy(s.Backup(0), s.FilePath(0), true);
            var state = Data.Json().Deserialize<Journal>(File.ReadAllText(s.State));
            state.Phase = "Prepared"; File.WriteAllText(s.State, Data.Json().Serialize(state));
            Assert(s.Engine.Check().Contains("interrupted"), "Recovery detected");
            Reject(() => s.Engine.Install());
            s.Engine.Uninstall(); s.Originals();
        }));
        Test("Interrupted restore resumes", () => With(fixture, s =>
        {
            s.Engine.Install();
            File.Copy(s.Backup(2), s.FilePath(2), true);
            var state = Data.Json().Deserialize<Journal>(File.ReadAllText(s.State)); state.Phase = "Restoring";
            File.WriteAllText(s.State, Data.Json().Serialize(state));
            s.Engine.Uninstall(); s.Originals();
        }));
        Test("Changed installed file blocks the entire restore", () => With(fixture, s =>
        {
            s.Engine.Install(); File.AppendAllText(s.FilePath(3), "another mod");
            byte[][] before = Enumerable.Range(0, s.F.Patch.Files.Length).Select(i => File.ReadAllBytes(s.FilePath(i))).ToArray();
            Reject(() => s.Engine.Uninstall());
            for (int i = 0; i < s.F.Patch.Files.Length; i++) Assert(before[i].SequenceEqual(File.ReadAllBytes(s.FilePath(i))), "Partial restore occurred");
        }));
        Test("Corrupt backup blocks the entire restore", () => With(fixture, s =>
        {
            s.Engine.Install(); File.AppendAllText(s.Backup(3), "corruption");
            Reject(() => s.Engine.Uninstall()); s.Patched();
        }));
        Test("Manual install is recognized without inventing backups", () => With(fixture, s =>
        {
            for (int i = 0; i < s.F.Patch.Files.Length; i++) File.WriteAllBytes(s.FilePath(i), Convert.FromBase64String(s.F.Targets[i]));
            Assert(s.Engine.Check().Contains("no original backups"), "Manual install message");
            s.Engine.Install(); s.Patched();
            Assert(!File.Exists(s.Backup(0)), "No fake original backup");
            Reject(() => s.Engine.Uninstall());
        }));
        Test("Mixed manual files refused", () => With(fixture, s =>
        {
            File.WriteAllBytes(s.FilePath(0), Convert.FromBase64String(s.F.Targets[0]));
            Reject(() => s.Engine.Install());
            Assert(File.ReadAllBytes(s.FilePath(1)).SequenceEqual(Convert.FromBase64String(s.F.Originals[1])), "Original SWF preserved");
        }));
        Test("Concurrent installer lock prevents writes", () => With(fixture, s =>
        {
            Directory.CreateDirectory(Path.Combine(s.Root, Installer.BackupFolder));
            using (var held = new FileStream(Path.Combine(s.Root, Installer.BackupFolder, "install.lock"), FileMode.Create, FileAccess.ReadWrite, FileShare.None))
                Reject(() => s.Engine.Install());
            s.Originals();
        }));
        Test("Tampered backup record cannot choose restore paths", () => With(fixture, s =>
        {
            s.Engine.Install();
            var state = Data.Json().Deserialize<Journal>(File.ReadAllText(s.State)); state.Files[0].Path = "../outside.exe";
            File.WriteAllText(s.State, Data.Json().Serialize(state)); Reject(() => s.Engine.Uninstall()); s.Patched();
        }));
        Test("Path traversal in a patch is rejected", () => With(fixture, s =>
        {
            s.F.Patch.Files[0].Path = "../outside.exe"; Reject(() => { var engine = s.Engine; engine.Check(); });
        }));
        Test("SWF checksum and expanded length are checked", () => With(fixture, s =>
        {
            byte[] bad = Convert.FromBase64String(s.F.Originals[1]); bad[bad.Length - 1] ^= 1;
            Reject(() => Data.Canonical(bad, "swf"));
            bad = Convert.FromBase64String(s.F.Originals[1]); bad[4] ^= 1; Reject(() => Data.Canonical(bad, "swf"));
        }));
        Test("Target hash mismatch refuses patch before writes", () => With(fixture, s =>
        {
            s.F.Patch.Files[4].TargetSha256 = new string('a', 64);
            Reject(() => s.Engine.Install()); s.Originals();
        }));
        Test("Embedded real manifest has exactly the supported targets", () =>
        {
            Manifest m = Data.Json().Deserialize<Manifest>(File.ReadAllText(args[1]));
            Assert(m.Files.Length == 5 && m.Files[0].Path == "AoW3_Debug.exe" && m.Files[4].Path == "AoW3.exe", "Normal and debug profile");
            Assert(m.Files[0].OriginalSha256 == "233584a414e16f624a5531b10e1491896e4b17a074e585364fec7d11c692d763", "Original build");
            Assert(m.Files[0].TargetSha256 == "bff0fbed9a5ec1742641812ee963c7b7f17d08c16e83ec2ec2195fe17e956e81", "Debug tooltip fix output");
            Assert(m.Files[4].OriginalSha256 == "9fd625d451ae534cf877b7850c614677f4d2d6209741bf85035e79f081a796d4", "Normal original build");
            Assert(m.Files[4].TargetSha256 == "c2b16440c0de6dbbe326306374379cfa99fdee0ec18d2b3c5b993a8beef24d64", "Normal tooltip fix output");
        });
        Console.WriteLine("RESULT: " + passed + " passed, " + failed + " failed");
        return failed == 0 ? 0 : 1;
    }
}
