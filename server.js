const express = require("express");
const mysql = require("mysql2");

const app = express();

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use(express.static("public"));

const db = mysql.createConnection({
  host: "localhost",
  user: "root",
  password: "root123",
  database: "synapse",
});

db.connect((err) => {
  if (err) throw err;
  console.log("Database connected");
});

app.get("/", (req, res) => {
  res.sendFile(__dirname + "/public/index.html");
});

app.post("/signup", (req, res) => {
  const { username, email, password } = req.body;

  db.query(
    "INSERT INTO users(username,email,password) VALUES(?,?,?)",
    [username, email, password],
    (err, result) => {
      if (err) throw err;
      res.send("Signup successful");
    },
  );
});

app.post("/login", (req, res) => {
  const { email, password } = req.body;

  db.query(
    "SELECT * FROM users WHERE email=? AND password=?",
    [email, password],
    (err, result) => {
      if (result.length > 0) {
        res.send("Login success");
      } else {
        res.send("Invalid credentials");
      }
    },
  );
});

app.listen(3000, () => {
  console.log("Server running on port 3000");
});
