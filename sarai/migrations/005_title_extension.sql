-- Titles defaulted from the upload's filename kept its extension, which then
-- showed in the minutes heading and in downloads ("meeting.mp4.pdf"). New
-- uploads strip it in the API; this cleans the meetings created before that,
-- and the title stored inside their minutes.
UPDATE meetings SET title = rtrim(substr(title, 1, length(title) - 4))
 WHERE lower(substr(title, -4)) IN ('.mp3', '.m4a', '.wav', '.ogg', '.mp4')
   AND length(title) > 4;
UPDATE meetings SET title = rtrim(substr(title, 1, length(title) - 5))
 WHERE lower(substr(title, -5)) = '.flac' AND length(title) > 5;
UPDATE summaries SET data = json_set(data, '$.title',
       (SELECT m.title FROM meetings m WHERE m.id = summaries.meeting_id))
 WHERE json_extract(data, '$.title') =
       (SELECT m.source_file FROM meetings m WHERE m.id = summaries.meeting_id);
