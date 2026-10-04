# User Guide

This guide is for instructors and academic staff who use Attendance Manager to track course
attendance.

## 1. Install

1. Run **`Attendance Manager Setup.exe`**. No administrator rights are needed.
2. Keep **Create a desktop shortcut** selected if you want one, then finish the wizard.
3. Open **Attendance Manager** from the desktop or the Start Menu.

The application works completely offline. To update, run the newer installer; your courses are
kept. Uninstalling (Windows *Settings → Apps*) also keeps your data.

> If Windows SmartScreen shows "Windows protected your PC", choose **More info → Run anyway**.
> This appears because the installer is not yet code-signed.

## 2. Choose the language

Click **العربية** or **English** in the top bar (also available under *Settings*). The whole
interface switches immediately; Arabic uses a right-to-left layout. Your choice is remembered the
next time you open the application.

## 3. Create a course

1. Click **Create course**.
2. Enter the course name, and optionally the section, semester, year and notes. Click **Next**.
3. Click **Browse for file…** (or drag the file in) and choose the master student list, for example
   `00.xls`.
4. Check the preview: it shows how many students were found and which columns hold the student ID
   and the name. If something looks wrong, click **Adjust columns** and pick the right ones.
5. Click **Create course**.

All other columns of the master list (major, status, …) are kept and shown with each student.

## 4. Add attendance after each lecture

1. Click **Add attendance** (or press `Ctrl+U`, or drag the file anywhere onto the window).
2. Choose the lecture's attendance file, for example a Microsoft Teams attendance report.
3. Review the result before saving:
   - **Present**: students on the master list whose ID appears in the file;
   - **Absent**: students on the master list who are not in the file;
   - **Not on master list**: the organizer, guests or students from other sections. They are shown
     for information and never counted.
4. Check the **session title** and the **lecture date** (taken from the file when available).
5. Click **Save attendance**. Nothing is saved before this.

If you choose a file that was already uploaded, even under a different name, a warning explains
that the lecture would be counted twice, and saving requires an explicit confirmation.

### Supported files

| Format | Notes |
|---|---|
| `.xls` (Excel 97–2003) | including Microsoft Teams attendance reports |
| `.xlsx`, `.xlsm` | modern Excel workbooks |
| `.csv`, `.tsv`, `.txt` | UTF-8, UTF-16 (Teams downloads), Arabic/Western Windows encodings |
| HTML saved as `.xls` | common in university portals |

Students are always matched by **student ID**, never by name or row order. IDs written as numbers,
as text, inside e-mail addresses (`202400123@university.edu`) or with extra spaces are recognized
as the same student.

## 5. Follow the course

- **Dashboard**: total students, sessions, average attendance, present and absent records,
  students with perfect attendance, students with absences, students at risk, an attendance trend
  per lecture and the attendance distribution. Click a card to see the matching students.
- **Students**: search (`Ctrl+F`), sort and filter all students. Double-click a student to see
  their lecture-by-lecture history.
- **Attendance Sessions**: every uploaded lecture. Open a session to review it, open the original
  file, export it, rename it, or remove it from the statistics. Removed sessions can be restored.

### Status levels

| Status | Meaning (defaults, configurable in *Settings*) |
|---|---|
| Perfect | 100 % attendance |
| Good | at or above the warning limit (85 %) |
| Warning | between the at-risk limit (75 %) and the warning limit |
| At risk | below the at-risk limit (75 %) |

Attendance % = lectures attended ÷ lectures held since the student joined the course.

## 6. Export reports

Open **Reports** and click **Export report (Excel)…** (`Ctrl+E`). The workbook contains:

| Sheet | Contents |
|---|---|
| Summary | course overview, key figures and charts |
| Cumulative Attendance | every student with all master-list columns, present, absent, % and status |
| Session by Session | a P/A grid of every student across every lecture |
| Absence Ranking | students ordered by number of absences |
| Highest Attendance | students ordered by attendance % |
| At-Risk Students | students below the at-risk limit, plus those in the warning band |
| Student Details | one row per student per lecture |

The report is written in the current interface language. A single lecture can be exported from
the *Attendance Sessions* page.

## 7. Backups

- A backup is made automatically once a day; the last 14 are kept by default.
- *Backup & Restore → Back up now…* saves a single `.zip` file anywhere, for example a USB drive.
- **Restore from file…** (or select a listed backup and **Restore selected…**) checks the backup
  thoroughly before using it and makes a safety backup of the current data first, so a restore
  can always be undone.

Your data is stored in `%LOCALAPPDATA%\AttendanceManager`. *Settings → Data storage* shows the
exact folder and opens it.

## 8. Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+1` … `Ctrl+7` | Dashboard, Courses, Sessions, Students, Reports, Settings, Backup |
| `Ctrl+N` | Create course |
| `Ctrl+U` | Add attendance |
| `Ctrl+F` | Search students |
| `Ctrl+E` | Export the Excel report |
| `Enter` / double-click | Open the selected student or session |
| `F5` | Refresh |

## 9. Troubleshooting

| Problem | What to do |
|---|---|
| "No students were found in this file" | Make sure it is the master student list and that it contains a column of student IDs. |
| "The student ID column could not be detected automatically" | Choose the ID column yourself on the column screen that follows. |
| The wrong column was used | Click **Adjust columns…** on the review screen and select the ID and name columns. |
| The lecture date is wrong | Change it in the **Lecture date** field before saving, or rename the session later. |
| A lecture was uploaded by mistake | *Attendance Sessions* → select it → **More → Remove from statistics** (it can be restored). |
| The report cannot be saved | Close the workbook in Excel if it is open, then export again. |
| Antivirus blocks the application | The application is not yet code-signed; ask your IT department to allow `AttendanceManager.exe`. |
| "Attendance Manager is already open" | Only one window can use the data at a time; switch to the open window. |
