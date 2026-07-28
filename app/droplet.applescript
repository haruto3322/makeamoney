-- カット表作成アプリのドロップレット。
-- build_app.command が __REPO_ROOT__ を実際のパスに置換してから osacompile でビルドする。
-- 実処理は app/cutsheet.sh 側にあり、ここは Terminal を開いて渡すだけに留めている。

on run
	-- アイコンをダブルクリックした場合はファイル選択ダイアログを出す。
	set videoFile to choose file with prompt "カット表を作る参照動画を選んでください"
	processVideo(POSIX path of videoFile)
end run

on open droppedItems
	-- アイコンに動画をドラッグ&ドロップした場合。
	repeat with anItem in droppedItems
		processVideo(POSIX path of anItem)
	end repeat
end open

on processVideo(videoPath)
	set repoRoot to "__REPO_ROOT__"
	set runnerScript to quoted form of (repoRoot & "/app/cutsheet.sh")
	set quotedVideo to quoted form of videoPath
	tell application "Terminal"
		activate
		do script (runnerScript & " " & quotedVideo)
	end tell
end processVideo
