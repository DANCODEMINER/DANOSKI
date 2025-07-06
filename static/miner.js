// Toggle menu in login page
function toggleMenu() {
  const menu = document.getElementById("menu");
  menu.style.display = menu.style.display === "flex" ? "none" : "flex";
}

function showForm(formType) {
  document.getElementById("login-form").style.display = formType === "login" ? "block" : "none";
  document.getElementById("register-form").style.display = formType === "register" ? "block" : "none";
  document.getElementById("forgot-form").style.display = formType === "forgot" ? "block" : "none";
  document.getElementById("otp-form").style.display = formType === "otp-form" ? "block" : "none";
  document.getElementById("pin-form").style.display = formType === "pin-form" ? "block" : "none";
  document.getElementById("pin-verify-form").style.display = formType === "pin-verify" ? "block" : "none";
  document.getElementById("dashboard-page").style.display = formType === "dashboard" ? "block" : "none";
}

function signupUser() {
  const fullName = document.getElementById("signup-name").value.trim();
  const country = document.getElementById("signup-country").value.trim();
  const email = document.getElementById("signup-email").value.trim();
  const password = document.getElementById("signup-password").value.trim();
  const otpMsg = document.getElementById("otp-message");

  const signupData = {
    full_name: fullName,
    country: country,
    email: email,
    password: password
  };

  fetch("https://danoski-backend.onrender.com/user/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(signupData)
  })
  .then(res => res.json().then(data => ({ ok: res.ok, data })))
  .then(({ ok, data }) => {
    if (ok) {
      localStorage.setItem("name", fullName);
      localStorage.setItem("country", country);
      localStorage.setItem("email", email);
      localStorage.setItem("password", password);

      otpMsg.style.color = "green";
      otpMsg.innerText = "✅ OTP sent to your email.";
      document.getElementById("otp-email").value = email;
      showForm("otp-form");
      otpMsg.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      otpMsg.style.color = "red";
      otpMsg.innerText = "❌ " + (data.error || "Signup failed.");
      otpMsg.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    setTimeout(() => {
      otpMsg.innerText = "";
    }, 5000);
  })
  .catch(err => {
    otpMsg.style.color = "orange";
    otpMsg.innerText = "⚠️ Failed to connect to server.";
    otpMsg.scrollIntoView({ behavior: "smooth", block: "center" });
    console.error(err);
  });
}

function verifyOtp() {
  const email = document.getElementById("otp-email").value.trim();
  const otp = document.getElementById("otp-code").value.trim();
  const otpMsg = document.getElementById("otp-message");

  fetch("https://danoski-backend.onrender.com/user/verify-otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, otp })
  })
  .then(res => res.json().then(data => ({ ok: res.ok, data })))
  .then(({ ok, data }) => {
    if (ok) {
      otpMsg.style.color = "green";
      otpMsg.innerText = "✅ OTP verified! Set your PIN.";
      showForm("pin-form");
    } else {
      otpMsg.style.color = "red";
      otpMsg.innerText = "❌ " + (data.error || "Verification failed.");
    }
  })
  .catch(err => {
    otpMsg.style.color = "orange";
    otpMsg.innerText = "⚠️ Failed to connect to server.";
    console.error(err);
  });
}

function loginUser() {
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value.trim();

  const payload = { email, password };

  fetch("https://danoski-backend.onrender.com/user/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
  .then(res => res.json().then(data => ({ ok: res.ok, data })))
  .then(({ ok, data }) => {
    if (ok) {
      localStorage.setItem("loginEmail", email);
      alert("✅ Login successful. Please verify your PIN.");
      showForm("pin-verify");
    } else {
      alert("❌ " + data.error);
    }
  })
  .catch(err => {
    alert("⚠️ Failed to connect to server.");
    console.error(err);
  });
}

function setUserPin() {
  const pin = document.getElementById("pin1").value +
              document.getElementById("pin2").value +
              document.getElementById("pin3").value +
              document.getElementById("pin4").value;

  const full_name = localStorage.getItem("name");
  const country = localStorage.getItem("country");
  const email = localStorage.getItem("email");
  const password = localStorage.getItem("password");

  if (pin.length !== 4) {
    document.getElementById("pin-message").innerText = "Please enter a 4-digit PIN.";
    return;
  }

  fetch("https://danoski-backend.onrender.com/user/create-account", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ full_name, country, email, password, pin })
  })
    .then(res => res.json().then(data => ({ ok: res.ok, data })))
    .then(({ ok, data }) => {
      if (ok) {
        alert("✅ Account created successfully!");
        localStorage.setItem("isLoggedIn", "true");
        showDashboard();
      } else {
        alert("❌ " + data.error);
      }
    })
    .catch(err => {
      alert("⚠️ Failed to connect to server.");
      console.error(err);
    });
}

// === PIN Input Activation ===
function bindPinInputs() {
  const inputs = ["pin1", "pin2", "pin3", "pin4"];
  inputs.forEach((id, index) => {
    const input = document.getElementById(id);
    if (input) {
      input.addEventListener("input", () => {
        input.value = input.value.replace(/[^0-9]/g, "");
        if (input.value.length === 1 && index < inputs.length - 1) {
          const next = document.getElementById(inputs[index + 1]);
          if (next) next.focus();
        }
        checkPinLength();
      });

      input.addEventListener("keydown", (e) => {
        if (e.key === "Backspace" && input.value === "" && index > 0) {
          const prev = document.getElementById(inputs[index - 1]);
          if (prev) prev.focus();
        }
      });
    }
  });
}

function checkPinLength() {
  const pin = document.getElementById("pin1").value +
              document.getElementById("pin2").value +
              document.getElementById("pin3").value +
              document.getElementById("pin4").value;

  const btn = document.getElementById("create-account-btn");
  if (btn) {
    if (pin.length === 4) {
      btn.disabled = false;
      btn.style.opacity = "1";
      btn.style.cursor = "pointer";
    } else {
      btn.disabled = true;
      btn.style.opacity = "0.5";
      btn.style.cursor = "not-allowed";
    }
  }
}

function logout() {
  alert("Logging out...");
  document.getElementById("dashboard-page").style.display = "none";
  document.getElementById("login-page").style.display = "block";
  showForm("login");
}

function showDashboard() {
  document.getElementById("login-form").style.display = "none";
  document.getElementById("register-form").style.display = "none";
  document.getElementById("forgot-form").style.display = "none";
  document.getElementById("otp-form").style.display = "none";
  document.getElementById("pin-form").style.display = "none";
  document.getElementById("pin-verify-form").style.display = "none";
  document.getElementById("dashboard-page").style.display = "block";
}

let btcValue = 0.00000000;
setInterval(() => {
  const btcCounter = document.getElementById("btc-counter");
  if (btcCounter) {
    btcValue += 0.00000001;
    btcCounter.innerText = btcValue.toFixed(8) + " BTC";
  }
}, 1000);

// === DOMContentLoaded Init ===
document.addEventListener("DOMContentLoaded", () => {
  if (localStorage.getItem("isLoggedIn") === "true") {
    showDashboard();
  }

  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", function (e) {
      e.preventDefault();
      loginUser();
    });
  }

  const forgotForm = document.getElementById("forgot-form");
  if (forgotForm) {
    forgotForm.addEventListener("submit", function (e) {
      e.preventDefault();
      alert("Forgot password functionality to be implemented");
    });
  }

  bindPinInputs();
});
