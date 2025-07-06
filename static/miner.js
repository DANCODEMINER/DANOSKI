// Toggle menu in login page
function toggleMenu() {
  const menu = document.getElementById("menu");
  menu.style.display = menu.style.display === "flex" ? "none" : "flex";
}

let signupData = {};

async function signupUser() {
  const fullName = document.getElementById("signup-name").value.trim();
  const country = document.getElementById("signup-country").value.trim();
  const email = document.getElementById("signup-email").value.trim();
  const password = document.getElementById("signup-password").value.trim();
  const signupMsg = document.getElementById("otp-message"); // Reusing otp-message element for messages

  signupData = {
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

    if (res.ok) {
      otpMsg.style.color = "green";
      otpMsg.innerText = "✅ OTP sent to your email.";
      showForm("otp-form");  // make sure your showForm uses "otp" string here for otp-form
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
      otpMsg.innerText = "✅ OTP verified. Proceed to set your PIN.";
      showForm("setpin");
      document.getElementById("pin-email").value = email;
    } else {
      otpMsg.style.color = "red";
      otpMsg.innerText = "❌ " + (data.error || "Invalid OTP.");
    }
  } catch (err) {
    otpMsg.style.color = "orange";
    otpMsg.innerText = "⚠️ Failed to connect to server.";
    console.error(err);
  }

  // Clear OTP input and hide message after 5 seconds
  document.getElementById("otp-code").value = "";
  setTimeout(() => {
    otpMsg.innerText = "";
  }, 5000);
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
  const email = document.getElementById("pin-email").value.trim();
  const pinMsg = document.getElementById("pin-message");

  const pin = document.getElementById("pin1").value +
              document.getElementById("pin2").value +
              document.getElementById("pin3").value +
              document.getElementById("pin4").value;

  const confirmPin = document.getElementById("conf1").value +
                     document.getElementById("conf2").value +
                     document.getElementById("conf3").value +
                     document.getElementById("conf4").value;

  if (pin.length !== 4 || confirmPin.length !== 4) {
    pinMsg.style.color = "orange";
    pinMsg.innerText = "⚠️ Please enter 4 digits in both PIN fields.";
    return;
  }

  if (pin !== confirmPin) {
    pinMsg.style.color = "red";
    pinMsg.innerText = "❌ PIN mismatch. Please try again.";
    return;
  }

  const payload = {
    ...signupData,
    pin: pin
  };

  try {
    const res = await fetch("https://danoski-backend.onrender.com/user/create-account", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.ok) {
      pinMsg.style.color = "green";
      pinMsg.innerText = "✅ Account created successfully!";
      setTimeout(() => {
        showForm("login");
        pinMsg.innerText = "";
      }, 2000);
    } else {
      pinMsg.style.color = "red";
      pinMsg.innerText = "❌ " + (data.error || "Failed to create account.");
    }
  } catch (err) {
    pinMsg.style.color = "orange";
    pinMsg.innerText = "⚠️ Failed to connect to server.";
    console.error(err);
  }
}

async function verifyLoginPin() {
  const email = localStorage.getItem("loginEmail");
  const pin = 
    document.getElementById("pin1").value +
    document.getElementById("pin2").value +
    document.getElementById("pin3").value +
    document.getElementById("pin4").value;
  const pinMsg = document.getElementById("otp-message"); // You can create a similar message element for PIN form or reuse

  if (pin.length !== 4) {
    otpMsg.style.color = "orange";
    otpMsg.innerText = "⚠️ Please enter your 4-digit PIN.";
    otpMsg.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => { otpMsg.innerText = ""; }, 5000);
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
      document.getElementById("login-page").style.display = "none";
      document.getElementById("dashboard-page").style.display = "block";
    } else {
      otpMsg.style.color = "red";
      otpMsg.innerText = "❌ " + (data.error || "Invalid PIN.");
      otpMsg.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => { otpMsg.innerText = ""; }, 5000);
    }
  } catch (err) {
    otpMsg.style.color = "orange";
    otpMsg.innerText = "⚠️ Failed to verify PIN.";
    otpMsg.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => { otpMsg.innerText = ""; }, 5000);
    console.error(err);
  }
}


function showForm(formType) {
  document.getElementById("login-form").style.display = formType === "login" ? "block" : "none";
  document.getElementById("register-form").style.display = formType === "register" ? "block" : "none";
  document.getElementById("forgot-form").style.display = formType === "forgot" ? "block" : "none";
  document.getElementById("otp-form").style.display = formType === "otp-form" ? "block" : "none";  // added otp here
  document.getElementById("pin-form").style.display = formType === "pin" ? "block" : "none";  // add pin if you want
  document.getElementById("pin-verify-form").style.display = formType === "pin-verify" ? "block" : "none";
}

// On login success, switch to dashboard
function loginSuccess() {
  document.getElementById("login-page").style.display = "none";
  document.getElementById("dashboard-page").style.display = "block";
}

// Sidebar toggle for dashboard
function toggleSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("overlay");
  const isOpen = sidebar.classList.toggle("active");
  overlay.style.display = isOpen ? "block" : "none";
}

// Logout user and go back to login page
function logout() {
  alert("Logging out...");
  document.getElementById("dashboard-page").style.display = "none";
  document.getElementById("login-page").style.display = "block";
  showForm('login');
}

// BTC counter animation on dashboard
let btcValue = 0.00000000;
setInterval(() => {
  const btcCounter = document.getElementById("btc-counter");
  if (btcCounter) {
    btcValue += 0.00000001;
    btcCounter.innerText = btcValue.toFixed(8) + " BTC";
  }
}, 1000);

// Attach form submit event listeners for future backend integration
document.getElementById('login-form').addEventListener('submit', function(e) {
  e.preventDefault();
  // TODO: connect login to backend here
  loginSuccess();
});

document.getElementById('forgot-form').addEventListener('submit', function(e) {
  e.preventDefault();
  // TODO: connect forgot password to backend here
  alert('Forgot password functionality to be implemented');
});

document.addEventListener("DOMContentLoaded", () => {
  const pinInputs = document.querySelectorAll(".pin-input");

  pinInputs.forEach((input, index) => {
    input.addEventListener("input", () => {
      // Allow only digits
      input.value = input.value.replace(/[^0-9]/g, "");

      // Move to next input if one digit entered
      if (input.value.length === 1 && index < pinInputs.length - 1) {
        pinInputs[index + 1].focus();
      }
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && input.value === "" && index > 0) {
        pinInputs[index - 1].focus();
      }
    });
  });
});

document.addEventListener("DOMContentLoaded", () => {
  const pinInputs = document.querySelectorAll(".pin-input");

  pinInputs.forEach((input, index) => {
    input.addEventListener("input", () => {
      // Allow only digits
      input.value = input.value.replace(/[^0-9]/g, "");

      // Move to next input if one digit is entered
      if (input.value.length === 1 && index < pinInputs.length - 1) {
        pinInputs[index + 1].focus();
      }
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && input.value === "" && index > 0) {
        pinInputs[index - 1].focus();
      }
    });
  });
});
