//
// Author: Vinhthuy Phan, 2018
//
package main

import (
	"database/sql"
	"fmt"
	_ "github.com/mattn/go-sqlite3"
	"log"
	"time"
)

func create_tables() {
	execSQL := func(s string) {
		sql_stmt, err := Database.Prepare(s)
		if err != nil {
			log.Fatal(err)
		}
		sql_stmt.Exec()
	}
	execSQL("create table if not exists student (id integer primary key, name text unique, password text)")
	execSQL("create table if not exists teacher (id integer primary key, name text unique, password text)")
	execSQL("create table if not exists attendance (id integer primary key, stid integer, at timestamp)")
	execSQL("create table if not exists tag (id integer primary key, description text unique)")
	execSQL("create table if not exists problem (id integer primary key, tid integer, content blob, answer text, filename text, merit integer, effort integer, attempts integer, tag integer, at timestamp)")
	execSQL("create table if not exists submission (id integer primary key, pid integer, sid integer, content blob, priority integer, at timestamp, completed timestamp)")
	execSQL("create table if not exists score (id integer primary key, pid integer, stid integer, tid integer, points integer, attempts integer, at timestamp, unique(pid,stid))")
	execSQL("create table if not exists feedback (id integer primary key, tid integer, stid integer, content text, date timestamp)")
	// foreign key example: http://www.sqlitetutorial.net/sqlite-foreign-key/
}

//-----------------------------------------------------------------
func init_database(db_name string) {
	var err error
	prepare := func(s string) *sql.Stmt {
		stmt, err := Database.Prepare(s)
		if err != nil {
			log.Fatal(err)
		}
		return stmt
	}

	Database, err = sql.Open("sqlite3", db_name)
	if err != nil {
		log.Fatal(err)
	}
	create_tables()
	AddStudentSQL = prepare("insert into student (name, password) values (?, ?)")
	AddTeacherSQL = prepare("insert into teacher (name, password) values (?, ?)")
	AddProblemSQL = prepare("insert into problem (tid, content, answer, filename, merit, effort, attempts, tag, at) values (?, ?, ?, ?, ?, ?, ?, ?, ?)")
	AddSubmissionSQL = prepare("insert into submission (pid, sid, content, priority, at) values (?, ?, ?, ?, ?)")
	AddSubmissionCompleteSQL = prepare("insert into submission (pid, sid, content, priority, at, completed) values (?, ?, ?, ?, ?, ?)")
	CompleteSubmissionSQL = prepare("update submission set completed=? where id=?")
	AddScoreSQL = prepare("insert into score (pid, stid, tid, points, attempts, at) values (?, ?, ?, ?, ?, ?)")
	AddFeedbackSQL = prepare("insert into feedback (tid, stid, content, date) values (?, ?, ?, ?)")
	UpdateScoreSQL = prepare("update score set tid=?, points=?, attempts=? where id=?")
	AddAttendanceSQL = prepare("insert into attendance (stid, at) values (?, ?)")
	AddTagSQL = prepare("insert into tag (description) values (?)")
	// Initialize passcode for current session and default board
	Passcode = RandStringRunes(12)
	Students[0] = &StudenInfo{
		Boards: make([]*Board, 0),
	}
}

//-----------------------------------------------------------------
// Add or update score based on a decision. If decision is "correct"
// a new problem, if there's one, is added to student's board.
//-----------------------------------------------------------------
func add_or_update_score(decision string, pid, stid, tid, partial_credits int) string {
	mesg := ""

	// Find score information for this student (stid) for this problem (pid)
	score_id, current_points, current_attempts, current_tid := 0, 0, 0, 0
	rows, _ := Database.Query("select id, points, attempts, tid from score where pid=? and stid=?", pid, stid)
	for rows.Next() {
		rows.Scan(&score_id, &current_points, &current_attempts, &current_tid)
		break
	}
	rows.Close()

	// Find merit points and effort points for this problem (pid)
	merit, effort := 0, 0
	rows, _ = Database.Query("select merit, effort from problem where id=?", pid)
	for rows.Next() {
		rows.Scan(&merit, &effort)
		break
	}
	rows.Close()

	// Determine points for this student
	points, teacher := 0, tid
	if decision == "correct" {
		points = merit
		mesg = "Answer is correct."
	} else {
		if partial_credits < merit {
			points = partial_credits
		} else {
			points = effort
		}

		// If the problem was previously graded correct, this submission
		// does not reduce it.  Grading is asynchronous.
		if points < current_points {
			points = current_points
			teacher = current_tid
		}
		mesg = "Answer is incorrect."
	}
	// m := add_next_problem_to_board(pid, stid, decision)
	// mesg = mesg + m

	// Add a new score or update a current score for this student & problem
	if score_id == 0 {
		_, err := AddScoreSQL.Exec(pid, stid, tid, points, current_attempts+1, time.Now())
		if err != nil {
			mesg = fmt.Sprintf("Unable to add score: %d %d %d", pid, stid, tid)
			writeLog(Config.LogFile, mesg)
			return mesg
		}
	} else {
		_, err := UpdateScoreSQL.Exec(teacher, points, current_attempts+1, score_id)
		if err != nil {
			mesg = fmt.Sprintf("Unable to update score: %d %d", teacher, score_id)
			writeLog(Config.LogFile, mesg)
			return mesg
		}
	}
	return mesg
}

//-----------------------------------------------------------------
func init_teacher(id int, password string) {
	Teacher[id] = password
}

//-----------------------------------------------------------------
// initialize once per session
//-----------------------------------------------------------------
func init_student(stid int, password string) {
	AddAttendanceSQL.Exec(stid, time.Now())

	BoardsSem.Lock()
	defer BoardsSem.Unlock()

	Students[stid] = &StudenInfo{
		Password:         password,
		Boards:           make([]*Board, 0),
		SubmissionStatus: 0,
	}

	// Student[stid] = password
	// MessageBoards[stid] = ""
	// Boards[stid] = make([]*Board, 0)

	for i := 0; i < len(Students[0].Boards); i++ {
		b := &Board{
			Content:      Students[0].Boards[i].Content,
			Answer:       Students[0].Boards[i].Answer,
			Attempts:     Students[0].Boards[i].Attempts,
			Filename:     Students[0].Boards[i].Filename,
			Pid:          Students[0].Boards[i].Pid,
			StartingTime: time.Now(),
		}
		Students[stid].Boards = append(Students[stid].Boards, b)
	}
}

//-----------------------------------------------------------------
func load_and_authorize_student(stid int, password string) bool {
	var pw string
	found := false
	rows, _ := Database.Query("select password from student where id=?", stid)
	for rows.Next() {
		rows.Scan(&pw)
		found = true
		break
	}
	rows.Close()
	if !found || pw != password {
		return false
	}
	init_student(stid, password)
	return true
}

//-----------------------------------------------------------------
func load_teachers() {
	rows, _ := Database.Query("select id, password from teacher")
	defer rows.Close()
	var password string
	var id int
	for rows.Next() {
		rows.Scan(&id, &password)
		Teacher[id] = password
	}
	Passcode = RandStringRunes(20)
}

//-----------------------------------------------------------------
