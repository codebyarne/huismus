# The desktop app

With the desktop app you use Huismus as an ordinary app on your Mac or
Windows PC, without a server. Your records then live on your own computer.
The app works on macOS 14 or newer with an Apple chip, and on Windows 10 or
newer.

## Opening it the first time

**Mac.** Apple hasn't signed the app, so macOS won't open it the first
time. Go to System Settings → Privacy & Security and choose **Open
Anyway**.

**Windows.** The installer isn't signed either. The first time, Windows
says "Windows protected your PC". Choose **More info** and then **Run
anyway**. You don't need administrator rights to install Huismus.

On Windows, Huismus needs Microsoft Edge WebView2 for its window. Windows 11
and an up-to-date Windows 10 already have it. If it's missing, Huismus asks
whether you want to download it from Microsoft now. Install it and open
Huismus again.

Want to look around first? On the empty overview, choose **Try with sample
data**. Huismus fills itself with examples. **Clear sample
data** removes them again.

## Opening and closing

When it opens, the window briefly says "Huismus is starting…". After that,
Huismus runs only on your own computer. Nobody can reach it from outside.
When you close the window, Huismus stops completely.

Huismus can only be open once at a time. If you open it again, the window
that's already open comes to the front.

If Huismus can't start, the window says so. You then see an error code and
the buttons **Try again** and **Save log file**. If you ask someone for
help, send the log file along.

## Setting a password

Huismus opens without a password, unless you set one under **Settings →
Password**. From then on the app asks for it every time you open it.

To change the password or turn it off, Huismus first asks for the current
one. The password is part of every backup. If you forget it, Huismus can't
get it back.

If you restore a backup from a server, such as a Raspberry Pi, the app from
then on asks for that server's password.

## Backups

Under **Settings → Backups** you choose a folder once. After that Huismus
makes a backup every day, as long as the app is open. Huismus suggests the
iCloud Drive, Google Drive, OneDrive and Dropbox folders it finds on your
computer. If Google Drive on Windows isn't on `G:`, choose it with **Other
folder…**. There's more in [Backups](back-ups.en.md).

## Updating to a new version

When it opens and then once a day, Huismus checks whether there's a new
version. That's the only thing Huismus asks the internet for by itself: the
public list of versions, nothing else. If you don't want that, turn it off
under **Settings → Updates**.

When there's a new version, you see a notice on the overview. Choose
**Update to …** and confirm. Huismus downloads the new version, checks it,
makes a backup, closes and opens again by itself in the new version. The
overview then says "Updated to …".

If updating doesn't work, the window says so, with the buttons **Restore
backup** and **Save log file**. Then install the previous version again.

## Where everything is

| What | Mac | Windows |
|---|---|---|
| Your records | `~/Library/Application Support/Huismus` | `%APPDATA%\Huismus` |
| Log file | `~/Library/Logs/Huismus/huismus.log` | `%LOCALAPPDATA%\Huismus\huismus.log` |
| Backups from before restoring, when no folder is chosen | `~/Library/Application Support/Huismus back-ups` | `%APPDATA%\Huismus back-ups` |
| The app itself | wherever you put `Huismus.app` | `%LOCALAPPDATA%\Programs\Huismus` |

## Removing Huismus

On a Mac, drag `Huismus.app` to the Bin. On Windows, remove Huismus through
Settings → Apps. Your records stay where they are. If you want those gone
too, first make a backup if you might still need it, then delete the folder
from the table above yourself.
