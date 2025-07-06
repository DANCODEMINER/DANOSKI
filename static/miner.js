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

let signupData = {};

async function signupUser() {
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

  try {
    const res = await fetch("https://danoski-backend.onrender.com/user/signup", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(signupData)
    });

    const data = await res.json();

    console.log("SIGNUP response:", data);
    console.log("RES status:", res.status);

    if (res.ok) {
      
      // ✅ Store data for PIN creation step
      localStorage.setItem("name", fullName);
      localStorage.setItem("country", country);
      localStorage.setItem("email", email);
      localStorage.setItem("password", password);

      // ✅ Continue with OTP flow
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
  } catch (err) {
    otpMsg.style.color = "orange";
    otpMsg.innerText = "⚠️ Failed to connect to server.";
    otpMsg.scrollIntoView({ behavior: "smooth", block: "center" });
    console.error(err);
  }

  setTimeout(() => {
    otpMsg.innerText = "";
  }, 5000);
}

async function verifyOtp() {
  const email = document.getElementById("otp-email").value.trim();
  const otp = document.getElementById("otp-code").value.trim();
  const otpMsg = document.getElementById("otp-message");

  try {
    const res = await fetch("https://danoski-backend.onrender.com/user/verify-otp", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email, otp })
    });

    const data = await res.json();

    if (res.ok) {
      otpMsg.style.color = "green";
      otpMsg.innerText = "✅ OTP verified! Set your PIN.";
      showForm("pin-form");
      attachPinListeners();
    } else {
      otpMsg.style.color = "red";
      otpMsg.innerText = "❌ " + (data.error || "Verification failed.");
    }
  } catch (err) {
    otpMsg.style.color = "orange";
    otpMsg.innerText = "⚠️ Failed to connect to server.";
    console.error(err);
  }
}

async function loginUser() {
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value.trim();

  const payload = { email, password };

  try {
    const res = await fetch("https://danoski-backend.onrender.com/user/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.ok) {
      // Save email temporarily for PIN verification
      localStorage.setItem("loginEmail", email);

      alert("✅ Login successful. Please verify your PIN.");
      showForm("pin-verify"); // Show PIN form
    } else {
      alert("❌ " + data.error);
    }
  } catch (err) {
    alert("⚠️ Failed to connect to server.");
    console.error(err);
  }
}

async function setUserPin() {
  const pin = document.getElementById("pin1").value +
              document.getElementById("pin2").value +
              document.getElementById("pin3").value +
              document.getElementById("pin4").value;

  const full_name = localStorage.getItem("name");
  const country = localStorage.getItem("country");
  const email = localStorage.getItem("email");
  const password = localStorage.getItem("password");

  const res = await fetch("https://danoski-backend.onrender.com/user/create-account", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      full_name,
      country,
      email,
      password,
      pin
    })
  });

  const data = await res.json();

  if (res.ok) {
    alert("✅ Account created successfully!");

    // ✅ Mark user as logged in
    localStorage.setItem("isLoggedIn", "true");

    // ✅ Show dashboard
    showDashboard();
  } else {
    alert("❌ " + data.error);
  }
} // ✅ This was the missing closing brace

async function verifyLoginPin() {
  const email = localStorage.getItem("loginEmail");
  const pin =
    document.getElementById("pin1").value +
    document.getElementById("pin2").value +
    document.getElementById("pin3").value +
    document.getElementById("pin4").value;
  const pinMsg = document.getElementById("pin-message");

  if (pin.length !== 4) {
    pinMsg.style.color = "orange";
    pinMsg.innerText = "⚠️ Please enter your 4-digit PIN.";
    pinMsg.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => { pinMsg.innerText = ""; }, 5000);
    return;
  }

  const payload = { email, pin };

  try {
    const res = await fetch("https://danoski-backend.onrender.com/user/verify-login-pin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.ok) {
      alert("✅ " + data.message);
      showDashboard();
    } else {
      pinMsg.style.color = "red";
      pinMsg.innerText = "❌ " + (data.error || "Invalid PIN.");
      pinMsg.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => { pinMsg.innerText = ""; }, 5000);
    }
  } catch (err) {
    pinMsg.style.color = "orange";
    pinMsg.innerText = "⚠️ Failed to verify PIN.";
    pinMsg.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => { pinMsg.innerText = ""; }, 5000);
    console.error(err);
  }
}

// Logout user and go back to login page
function logout() {
  alert("Logging out...");
  document.getElementById("dashboard-page").style.display = "none";
  document.getElementById("login-page").style.display = "block";
  showForm('login');
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

// Attach form submit event listeners for future backend integration
document.addEventListener("DOMContentLoaded", () => {
  // ✅ If already logged in, show dashboard
  if (localStorage.getItem("isLoggedIn") === "true") {
    showDashboard();
  }

  // ✅ Handle login form submission
  document.getElementById('login-form').addEventListener('submit', function(e) {
    e.preventDefault();
    loginSuccess(); // Replace with actual login logic
  });

  // ✅ Handle forgot password form submission
  document.getElementById('forgot-form').addEventListener('submit', function(e) {
    e.preventDefault();
    alert('Forgot password functionality to be implemented');
  });

  // ✅ Attach PIN inputs
  bindPinInputs(); // 👈 THIS is now your main handler
});

// ✅ PIN input auto-focus, match checking, and button activation
function bindPinInputs() {
  const inputs = [
    "pin1", "pin2", "pin3", "pin4",
    "conf1", "conf2", "conf3", "conf4"
  ];

  inputs.forEach(id => {
    const input = document.getElementById(id);
    if (input) {
      input.addEventListener("input", () => {
        input.value = input.value.replace(/[^0-9]/g, "");
        checkPinMatch();
        const index = inputs.indexOf(id);
        if (input.value.length === 1 && index < inputs.length - 1) {
          const nextInput = document.getElementById(inputs[index + 1]);
          if (nextInput) nextInput.focus();
        }
      });

      input.addEventListener("keydown", (e) => {
        if (e.key === "Backspace" && input.value === "") {
          const index = inputs.indexOf(id);
          if (index > 0) {
            const prevInput = document.getElementById(inputs[index - 1]);
            if (prevInput) prevInput.focus();
          }
        }
      });
    }
  });
}

// ✅ Live check for PIN match
function checkPinMatch() {
  const pin = document.getElementById("pin1").value +
              document.getElementById("pin2").value +
              document.getElementById("pin3").value +
              document.getElementById("pin4").value;

  const confirm = document.getElementById("conf1").value +
                  document.getElementById("conf2").value +
                  document.getElementById("conf3").value +
                  document.getElementById("conf4").value;

  const pinMsg = document.getElementById("pin-message");
  const btn = document.getElementById("create-account-btn");

  if (pin.length === 4 && confirm.length === 4) {
    if (pin === confirm) {
      pinMsg.style.color = "green";
      pinMsg.innerText = "✅ PINs match. You can now create your account.";
      btn.disabled = false;
      btn.style.opacity = "1";
      btn.style.cursor = "pointer";
    } else {
      pinMsg.style.color = "red";
      pinMsg.innerText = "❌ PIN mismatch. Please try again.";
      btn.disabled = true;
      btn.style.opacity = "0.5";
      btn.style.cursor = "not-allowed";
    }
  } else {
    pinMsg.innerText = "";
    btn.disabled = true;
    btn.style.opacity = "0.5";
    btn.style.cursor = "not-allowed";
  }
}

// ✅ Optional: Ensure dashboard loads on reload if logged in
document.addEventListener("DOMContentLoaded", () => {
  if (localStorage.getItem("isLoggedIn") === "true") {
    showDashboard();
  }
});
