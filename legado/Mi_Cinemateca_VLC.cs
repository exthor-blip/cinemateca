using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class CinematecaVlc
{
    private const string RegistryPath = @"Software\Classes\micinemateca-vlc\Locations";
    private const string ProtocolPrefix = "micinemateca-vlc:2edb98eeacf856ae70ca546d9b146615e179602bf6b3deab/";
    private static readonly Regex PayloadPattern = new Regex(@"\A[A-Za-z0-9_-]{2,7000}\z");
    private static readonly char[] InvalidSegmentChars = Path.GetInvalidFileNameChars();

    internal sealed class VideoRequest
    {
        public string SourceId { get; set; }
        public string SourceName { get; set; }
        public string Relative { get; set; }
        public string FileName { get; set; }
    }

    [STAThread]
    private static void Main(string[] args)
    {
        if (args.Length != 1 || !args[0].StartsWith(ProtocolPrefix, StringComparison.Ordinal)) return;
        try
        {
            VideoRequest request = ParseRequest(args[0]);
            string vlc = FindVlc();
            if (vlc == null) throw new InvalidOperationException("No pude encontrar la instalación de VLC.");
            string path = FindVideo(request);
            if (path == null) return;
            Process.Start(new ProcessStartInfo(vlc, "--one-instance -- \"" + path + "\"")
            {
                UseShellExecute = false,
                WorkingDirectory = Path.GetDirectoryName(vlc)
            });
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "Mi Cinemateca · VLC", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }

    internal static VideoRequest ParseRequest(string uri)
    {
        if (!uri.StartsWith(ProtocolPrefix, StringComparison.Ordinal)) throw new ArgumentException("Enlace de VLC inválido.");
        string payload = uri.Substring(ProtocolPrefix.Length);
        if (!PayloadPattern.IsMatch(payload)) throw new ArgumentException("Enlace de VLC inválido.");
        payload = payload.Replace('-', '+').Replace('_', '/');
        payload = payload.PadRight((payload.Length + 3) / 4 * 4, '=');
        var request = new JavaScriptSerializer().Deserialize<VideoRequest>(Encoding.UTF8.GetString(Convert.FromBase64String(payload)));
        if (request == null || String.IsNullOrWhiteSpace(request.SourceId) ||
            request.SourceId.Length > 512 || String.IsNullOrWhiteSpace(request.SourceName) ||
            request.SourceName.Length > 512 || request.Relative == null ||
            !IsSegment(request.FileName) ||
            !Regex.IsMatch(request.FileName, @"\.(mkv|mp4|avi|mov|wmv|m4v|webm|mpeg|mpg|ts)\z", RegexOptions.IgnoreCase))
            throw new ArgumentException("La ficha no contiene una ruta de video válida.");
        if (request.Relative.Length != 0)
        {
            foreach (string part in request.Relative.Split('/'))
                if (!IsSegment(part)) throw new ArgumentException("La ruta del video no es válida.");
        }
        return request;
    }

    private static bool IsSegment(string part)
    {
        return !String.IsNullOrWhiteSpace(part) && part != "." && part != ".." &&
            part.IndexOfAny(InvalidSegmentChars) < 0 && !part.EndsWith(".", StringComparison.Ordinal) &&
            !part.EndsWith(" ", StringComparison.Ordinal);
    }

    internal static string ResolveVideo(string root, VideoRequest request)
    {
        if (String.IsNullOrWhiteSpace(root) || !Path.IsPathRooted(root)) return null;
        string prefix = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        string relative = request.Relative.Replace('/', Path.DirectorySeparatorChar);
        string target = Path.GetFullPath(Path.Combine(prefix, relative, request.FileName));
        return target.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) && File.Exists(target) ? target : null;
    }

    private static string FindVideo(VideoRequest request)
    {
        string mapping;
        using (var sha = SHA256.Create())
            mapping = Convert.ToBase64String(sha.ComputeHash(Encoding.UTF8.GetBytes(request.SourceId)));

        string savedRoot;
        using (var locations = Registry.CurrentUser.OpenSubKey(RegistryPath))
            savedRoot = locations == null ? null : locations.GetValue(mapping) as string;

        string video = ResolveVideo(savedRoot, request);
        if (video != null) return video;

        using (var picker = new FolderBrowserDialog())
        {
            picker.Description = "Seleccioná la carpeta raíz de \"" + request.SourceName + "\" para abrir el video original en VLC.";
            picker.ShowNewFolderButton = false;
            if (Directory.Exists(savedRoot)) picker.SelectedPath = savedRoot;
            while (picker.ShowDialog() == DialogResult.OK)
            {
                video = ResolveVideo(picker.SelectedPath, request);
                if (video != null)
                {
                    using (var locations = Registry.CurrentUser.CreateSubKey(RegistryPath))
                        locations.SetValue(mapping, picker.SelectedPath, RegistryValueKind.String);
                    return video;
                }
                MessageBox.Show("No encontré el archivo en esa carpeta. Elegí la carpeta raíz con la que agregaste la colección.",
                    "Mi Cinemateca · VLC", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }
        return null;
    }

    private static string FindVlc()
    {
        const string appPath = @"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\vlc.exe";
        foreach (RegistryKey hive in new[] { Registry.CurrentUser, Registry.LocalMachine })
        {
            using (RegistryKey key = hive.OpenSubKey(appPath))
            {
                string path = key == null ? null : (key.GetValue("") as string);
                if (File.Exists(path)) return path;
            }
        }
        foreach (string folder in new[] { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                                         Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86) })
        {
            if (String.IsNullOrEmpty(folder)) continue;
            string path = Path.Combine(folder, "VideoLAN", "VLC", "vlc.exe");
            if (File.Exists(path)) return path;
        }
        return null;
    }
}
