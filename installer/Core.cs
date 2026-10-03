using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

namespace AoW3Mod
{
    public sealed class Operation
    {
        public int Offset { get; set; }
        public int Length { get; set; }
        public string Data { get; set; }
    }
    public sealed class PatchFile
    {
        public string Path { get; set; }
        public string Encoding { get; set; }
        public string OriginalSha256 { get; set; }
        public string TargetSha256 { get; set; }
        public int OriginalSize { get; set; }
        public int TargetSize { get; set; }
        public Operation[] Operations { get; set; }
    }
    public sealed class Manifest
    {
        public int Format { get; set; }
        public string Product { get; set; }
        public string Version { get; set; }
        public string Profile { get; set; }
        public PatchFile[] Files { get; set; }
    }
    public sealed class SavedFile
    {
        public string Path { get; set; }
        public string OriginalRawSha256 { get; set; }
        public string PatchedRawSha256 { get; set; }
    }
    public sealed class Journal
    {
        public string Product { get; set; }
        public string Profile { get; set; }
        public string Phase { get; set; }
        public SavedFile[] Files { get; set; }
    }
    public static class Data
    {
        public const int Limit = 67108864;
        public static JavaScriptSerializer Json()
        {
            return new JavaScriptSerializer { MaxJsonLength = 8 * 1024 * 1024, RecursionLimit = 64 };
        }
        public static string Hash(byte[] bytes)
        {
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        }
        public static byte[] Read(string path)
        {
            if (new FileInfo(path).Length > Limit)
                throw new InvalidDataException("File is larger than the supported build: " + path);
            return File.ReadAllBytes(path);
        }
        static uint Adler(byte[] bytes, int offset, int count)
        {
            uint a = 1, b = 0;
            for (int i = offset; i < offset + count; i++)
            {
                a = (a + bytes[i]) % 65521;
                b = (b + a) % 65521;
            }
            return (b << 16) | a;
        }
        public static byte[] Canonical(byte[] bytes, string encoding)
        {
            if (encoding == "raw") return bytes;
            if (encoding != "swf" || bytes.Length < 8 || bytes[1] != 87 || bytes[2] != 83)
                throw new InvalidDataException("Invalid SWF header.");
            uint declared = BitConverter.ToUInt32(bytes, 4);
            if (declared < 8 || declared > Limit)
                throw new InvalidDataException("Invalid SWF length.");
            if (bytes[0] == 70)
            {
                if (bytes.Length != declared) throw new InvalidDataException("SWF length mismatch.");
                return bytes;
            }
            if (bytes[0] != 67 || bytes.Length < 14 || (bytes[8] & 15) != 8 ||
                (bytes[8] >> 4) > 7 || (((int)bytes[8] << 8) + bytes[9]) % 31 != 0 ||
                (bytes[9] & 32) != 0)
                throw new InvalidDataException("Unsupported SWF compression.");
            byte[] result = new byte[declared];
            Buffer.BlockCopy(bytes, 0, result, 0, 8);
            result[0] = 70;
            using (var input = new MemoryStream(bytes, 10, bytes.Length - 14, false))
            using (var unzip = new DeflateStream(input, CompressionMode.Decompress))
            {
                int pos = 8, count;
                while (pos < result.Length && (count = unzip.Read(result, pos, result.Length - pos)) > 0)
                    pos += count;
                if (pos != result.Length || unzip.ReadByte() != -1)
                    throw new InvalidDataException("SWF decompressed length mismatch.");
            }
            int tail = bytes.Length - 4;
            uint checksum = ((uint)bytes[tail] << 24) | ((uint)bytes[tail + 1] << 16) |
                ((uint)bytes[tail + 2] << 8) | bytes[tail + 3];
            if (Adler(result, 8, result.Length - 8) != checksum)
                throw new InvalidDataException("SWF checksum mismatch.");
            return result;
        }
        public static byte[] Encode(byte[] bytes, string encoding)
        {
            if (encoding == "raw") return bytes;
            Canonical(bytes, encoding);
            using (var result = new MemoryStream())
            {
                result.Write(bytes, 0, 8);
                result.Position = 0;
                result.WriteByte(67);
                result.Position = 8;
                result.WriteByte(0x78);
                result.WriteByte(0x9c);
                using (var compressed = new MemoryStream())
                {
                    using (var zip = new DeflateStream(compressed, CompressionMode.Compress, true))
                        zip.Write(bytes, 8, bytes.Length - 8);
                    byte[] body = compressed.ToArray();
                    result.Write(body, 0, body.Length);
                }
                uint checksum = Adler(bytes, 8, bytes.Length - 8);
                result.WriteByte((byte)(checksum >> 24));
                result.WriteByte((byte)(checksum >> 16));
                result.WriteByte((byte)(checksum >> 8));
                result.WriteByte((byte)checksum);
                return result.ToArray();
            }
        }
        public static byte[] Apply(PatchFile file, byte[] original)
        {
            byte[] source = Canonical(original, file.Encoding);
            if (source.Length != file.OriginalSize || Hash(source) != file.OriginalSha256)
                throw new InvalidDataException("Unsupported original: " + file.Path);
            using (var result = new MemoryStream())
            {
                foreach (Operation op in file.Operations)
                {
                    if (op.Data != null)
                    {
                        byte[] literal = Convert.FromBase64String(op.Data);
                        if (result.Length + literal.Length > file.TargetSize)
                            throw new InvalidDataException("Patch exceeds its declared size.");
                        result.Write(literal, 0, literal.Length);
                    }
                    else
                    {
                        if (op.Offset < 0 || op.Length <= 0 || (long)op.Offset + op.Length > source.Length ||
                            result.Length + op.Length > file.TargetSize)
                            throw new InvalidDataException("Invalid patch copy range.");
                        result.Write(source, op.Offset, op.Length);
                    }
                }
                byte[] target = result.ToArray();
                if (target.Length != file.TargetSize || Hash(target) != file.TargetSha256)
                    throw new InvalidDataException("Patch verification failed: " + file.Path);
                byte[] output = Encode(target, file.Encoding);
                if (Hash(Canonical(output, file.Encoding)) != file.TargetSha256)
                    throw new InvalidDataException("Encoded patch verification failed.");
                return output;
            }
        }
        public static void DurableWrite(string path, byte[] bytes, bool createNew)
        {
            using (var stream = new FileStream(path, createNew ? FileMode.CreateNew : FileMode.Create,
                                               FileAccess.Write, FileShare.None))
            {
                stream.Write(bytes, 0, bytes.Length);
                stream.Flush(true);
            }
        }
    }

    public sealed class Installer
    {
        public const string BackupFolder = "AoW3ModBackup";
        readonly Manifest manifest;
        readonly string root;
        readonly string backup;
        readonly string statePath;
        // Test seam: production never sets this callback.
        public Action<int> AfterReplace;

        public Installer(string folder, Manifest patch)
        {
            manifest = patch;
            root = System.IO.Path.GetFullPath(folder).TrimEnd(System.IO.Path.DirectorySeparatorChar);
            if (!Directory.Exists(root)) throw new DirectoryNotFoundException("Select your game installation folder.");
            backup = SafePath(BackupFolder);
            statePath = SafePath(BackupFolder + "/state.json");
            if (patch == null || patch.Format != 1 || patch.Files == null || patch.Files.Length == 0 ||
                String.IsNullOrEmpty(patch.Product) || String.IsNullOrEmpty(patch.Profile))
                throw new InvalidDataException("Invalid patch manifest.");
            var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (PatchFile file in patch.Files)
            {
                SafePath(file.Path);
                if (!paths.Add(file.Path) || file.Path.StartsWith(BackupFolder, StringComparison.OrdinalIgnoreCase) ||
                    (file.Encoding != "raw" && file.Encoding != "swf") || file.OriginalSize < 0 ||
                    file.TargetSize <= 0 || file.TargetSize > Data.Limit || file.OriginalSize > Data.Limit ||
                    file.Operations == null || !ValidHash(file.OriginalSha256) || !ValidHash(file.TargetSha256))
                    throw new InvalidDataException("Invalid patch entry.");
            }
        }
        static bool ValidHash(string hash)
        {
            return hash != null && hash.Length == 64 && hash.All(c => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'));
        }
        string SafePath(string relative)
        {
            if (String.IsNullOrEmpty(relative) || System.IO.Path.IsPathRooted(relative) || relative.Contains(":") ||
                relative.Contains("\\") || relative.Split('/').Any(s => s == ".." || s == "." || s.Length == 0 || s.EndsWith(".") || s.EndsWith(" ")))
                throw new InvalidDataException("Unsafe file path.");
            string full = System.IO.Path.GetFullPath(System.IO.Path.Combine(root, relative.Replace('/', System.IO.Path.DirectorySeparatorChar)));
            if (!full.StartsWith(root + System.IO.Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("File path leaves the game folder.");
            for (string p = full; !String.IsNullOrEmpty(p); p = System.IO.Path.GetDirectoryName(p))
            {
                if ((File.Exists(p) || Directory.Exists(p)) && (File.GetAttributes(p) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Use the real game folder, not a symbolic link or junction: " + p);
            }
            return full;
        }
        string OriginalPath(int index) { return SafePath(BackupFolder + "/original-" + index + ".bak"); }
        string StagePath(int index) { return SafePath(BackupFolder + "/stage-" + index + ".tmp"); }
        FileStream Lock()
        {
            SafePath(BackupFolder);
            Directory.CreateDirectory(backup);
            return new FileStream(SafePath(BackupFolder + "/install.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        }
        int Status(PatchFile file, byte[] raw)
        {
            byte[] bytes = Data.Canonical(raw, file.Encoding);
            string hash = Data.Hash(bytes);
            if (bytes.Length == file.OriginalSize && hash == file.OriginalSha256) return 0;
            if (bytes.Length == file.TargetSize && hash == file.TargetSha256) return 1;
            throw new InvalidDataException("Unsupported or modified file: " + file.Path +
                "\r\nSHA-256 (" + (file.Encoding == "swf" ? "uncompressed SWF" : "file") + "): " + hash +
                "\r\nNo game files were changed. Restore the supported originals or use the correct installer version.");
        }
        byte[][] ReadAll()
        {
            return manifest.Files.Select(f => Data.Read(SafePath(f.Path))).ToArray();
        }
        public string Check()
        {
            byte[][] files = ReadAll();
            int[] states = manifest.Files.Select((f, i) => Status(f, files[i])).ToArray();
            if (File.Exists(statePath))
            {
                Journal saved = LoadJournal();
                ValidateBackups(saved);
                ValidateCurrent(saved);
                if (states.All(s => s == 1))
                    return "Installed for normal and debug mode. Original backups verified. Includes the preview HP tooltip fix.";
                if (states.All(s => s == 0)) return "Supported original files. Ready to install.";
                return "An interrupted installation can be recovered. Click Restore Originals, then install again.";
            }
            if (states.All(s => s == 0)) return "Supported original files. Ready to install.";
            if (states.All(s => s == 1))
                return "The same mod is already present, but this installer has no original backups. No changes are needed. Use your existing backups to uninstall.";
            throw new IOException("A mixture of original and previously patched files was found. Restore the original executables and three interface files before installing.");
        }
        Journal LoadJournal()
        {
            SafePath(BackupFolder + "/state.json");
            if (!File.Exists(statePath)) throw new IOException("No installer backup record exists. Restore from your own original backups.");
            Journal saved = Data.Json().Deserialize<Journal>(Encoding.UTF8.GetString(Data.Read(statePath)));
            if (saved == null || saved.Product != manifest.Product || saved.Profile != manifest.Profile ||
                saved.Files == null || saved.Files.Length != manifest.Files.Length)
                throw new InvalidDataException("Backup record belongs to a different patch. Keep the backup folder and use its original installer.");
            for (int i = 0; i < saved.Files.Length; i++)
                if (saved.Files[i] == null || saved.Files[i].Path != manifest.Files[i].Path ||
                    !ValidHash(saved.Files[i].OriginalRawSha256) || !ValidHash(saved.Files[i].PatchedRawSha256))
                    throw new InvalidDataException("Invalid backup record.");
            return saved;
        }
        void Save(Journal saved, string phase)
        {
            saved.Phase = phase;
            string temp = SafePath(BackupFolder + "/state.tmp");
            Data.DurableWrite(temp, Encoding.UTF8.GetBytes(Data.Json().Serialize(saved)), false);
            SafePath(BackupFolder + "/state.json");
            if (File.Exists(statePath)) File.Replace(temp, statePath, null);
            else File.Move(temp, statePath);
        }
        void ValidateBackups(Journal saved)
        {
            for (int i = 0; i < saved.Files.Length; i++)
            {
                byte[] original = Data.Read(OriginalPath(i));
                if (Data.Hash(original) != saved.Files[i].OriginalRawSha256 || Status(manifest.Files[i], original) != 0)
                    throw new InvalidDataException("Original backup failed verification: " + manifest.Files[i].Path + ". No files restored.");
            }
        }
        void ValidateCurrent(Journal saved)
        {
            for (int i = 0; i < saved.Files.Length; i++)
            {
                string actual = Data.Hash(Data.Read(SafePath(manifest.Files[i].Path)));
                if (actual != saved.Files[i].OriginalRawSha256 && actual != saved.Files[i].PatchedRawSha256)
                    throw new IOException("File changed since installation: " + manifest.Files[i].Path +
                        ". Restore was stopped to preserve your changes. Keep the AoW3ModBackup folder.");
            }
        }
        public string Install()
        {
            using (Lock())
            {
                byte[][] originals = ReadAll();
                int[] states = manifest.Files.Select((f, i) => Status(f, originals[i])).ToArray();
                Journal previous = File.Exists(statePath) ? LoadJournal() : null;
                if (previous != null) { ValidateBackups(previous); ValidateCurrent(previous); }
                if (states.All(s => s == 1))
                    return previous == null ? "Already installed manually. No files changed; original backups are not managed by this installer." : "Already installed. Original backups verified.";
                if (states.Any(s => s != 0))
                    throw new IOException(previous == null ? "Restore the original executables and three interface files before installing." : "Recover the interrupted install with Restore Originals first.");
                byte[][] outputs = manifest.Files.Select((f, i) => Data.Apply(f, originals[i])).ToArray();
                var saved = new Journal { Product = manifest.Product, Profile = manifest.Profile,
                    Files = manifest.Files.Select((f, i) => new SavedFile { Path = f.Path,
                        OriginalRawSha256 = Data.Hash(originals[i]), PatchedRawSha256 = Data.Hash(outputs[i]) }).ToArray() };
                for (int i = 0; i < originals.Length; i++)
                {
                    string original = OriginalPath(i);
                    if (File.Exists(original))
                    {
                        if (Data.Hash(Data.Read(original)) != saved.Files[i].OriginalRawSha256)
                            throw new IOException("Existing original backup differs. Keep it safe; this installer will not overwrite it.");
                    }
                    else Data.DurableWrite(original, originals[i], true);
                    Data.DurableWrite(StagePath(i), outputs[i], false);
                    if (Data.Hash(Data.Read(StagePath(i))) != saved.Files[i].PatchedRawSha256)
                        throw new IOException("Staged file verification failed.");
                }
                ValidateBackups(saved);
                // All files, deltas, backups and staged outputs are validated before replacing any game file.
                for (int i = 0; i < originals.Length; i++)
                    if (Data.Hash(Data.Read(SafePath(manifest.Files[i].Path))) != saved.Files[i].OriginalRawSha256)
                        throw new IOException("A game file changed during preparation. Close the game and try again.");
                Save(saved, "Prepared");
                try
                {
                    for (int i = 0; i < outputs.Length; i++)
                    {
                        string destination = SafePath(manifest.Files[i].Path);
                        if (Data.Hash(Data.Read(destination)) != saved.Files[i].OriginalRawSha256)
                            throw new IOException("A game file changed during installation.");
                        File.Replace(StagePath(i), destination, null);
                        if (AfterReplace != null) AfterReplace(i);
                        if (Data.Hash(Data.Read(destination)) != saved.Files[i].PatchedRawSha256)
                            throw new IOException("Installed file verification failed.");
                    }
                    Save(saved, "Installed");
                }
                catch (Exception installError)
                {
                    try { Restore(saved); }
                    catch (Exception restoreError)
                    {
                        throw new IOException("Installation stopped. Automatic restoration could not finish. Keep AoW3ModBackup and use Restore Originals.\r\n" +
                            installError.Message + "\r\nRestore: " + restoreError.Message, installError);
                    }
                    throw new IOException("Installation stopped; the original files were restored.\r\n" + installError.Message, installError);
                }
                return "Installed successfully for normal and debug mode. Includes the preview HP tooltip fix. Keep AoW3ModBackup to uninstall.";
            }
        }
        void Restore(Journal saved)
        {
            ValidateBackups(saved);
            ValidateCurrent(saved);
            Save(saved, "Restoring");
            for (int i = 0; i < saved.Files.Length; i++)
            {
                string path = SafePath(manifest.Files[i].Path);
                string hash = Data.Hash(Data.Read(path));
                if (hash == saved.Files[i].OriginalRawSha256) continue;
                if (hash != saved.Files[i].PatchedRawSha256) throw new IOException("A file changed while restoring: " + manifest.Files[i].Path);
                byte[] original = Data.Read(OriginalPath(i));
                if (Data.Hash(original) != saved.Files[i].OriginalRawSha256)
                    throw new IOException("A backup changed while restoring: " + manifest.Files[i].Path);
                Data.DurableWrite(StagePath(i), original, false);
                if (Data.Hash(Data.Read(StagePath(i))) != saved.Files[i].OriginalRawSha256)
                    throw new IOException("Staged restore verification failed: " + manifest.Files[i].Path);
                if (Data.Hash(Data.Read(path)) != saved.Files[i].PatchedRawSha256)
                    throw new IOException("A file changed while preparing restoration: " + manifest.Files[i].Path);
                File.Replace(StagePath(i), path, null);
                if (Data.Hash(Data.Read(path)) != saved.Files[i].OriginalRawSha256)
                    throw new IOException("Restored file verification failed: " + manifest.Files[i].Path);
            }
            Save(saved, "Uninstalled");
        }
        public string Uninstall()
        {
            using (Lock()) Restore(LoadJournal());
            return "Original files restored exactly. Backups have been kept; you can reinstall later.";
        }
    }
}
