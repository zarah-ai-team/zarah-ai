import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { login, register } from "../services/authService";
import { useAuth } from "../contexts/AuthContext";

const BG_PHOTOS = [
  { src: "/images/login/bg1.png", height: "82vh" },
  { src: "/images/login/bg2.png", height: "92vh" },
  { src: "/images/login/bg3.png", height: "88vh" },
  { src: "/images/login/bg4.png", height: "82vh" },
];

const GoogleIcon = () => (
  <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
    <path
      fill="#FFC107"
      d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z"
    />
    <path
      fill="#FF3D00"
      d="M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z"
    />
    <path
      fill="#4CAF50"
      d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238C29.211 35.091 26.715 36 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z"
    />
    <path
      fill="#1976D2"
      d="M43.611 20.083H42V20H24v8h11.303c-.792 2.237-2.231 4.166-4.087 5.571.001-.001.002-.001.003-.002l6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z"
    />
  </svg>
);

const inputCls =
  "h-12 bg-[#f5f5f5] border-[1.5px] border-[#444342] rounded-[8px] px-4 text-[#1f1f1f] text-[15px] font-medium placeholder:text-[#444342]/70 placeholder:font-medium outline-none focus:border-[#1f1f1f] focus:bg-white transition";

const Login = () => {
  const navigate = useNavigate();
  const { setAuth } = useAuth();

  const [tab, setTab] = useState("login");
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const [regUsername, setRegUsername] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regFullName, setRegFullName] = useState("");
  const [regPassword, setRegPassword] = useState("");

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) return;

    setLoading(true);
    setError(null);

    try {
      const data = await login(username.trim(), password);
      setAuth(data.user, data.access_token);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || "Invalid username or password.");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    if (!regUsername.trim() || !regEmail.trim() || !regPassword) return;

    setLoading(true);
    setError(null);

    try {
      await register(
        regUsername.trim(),
        regEmail.trim(),
        regPassword,
        regFullName.trim()
      );
      const data = await login(regUsername.trim(), regPassword);
      setAuth(data.user, data.access_token);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-[#f7f5ee] font-poppins">
      {/* Background image row */}
      <div className="pointer-events-none absolute inset-0 hidden md:block">
        <div className="flex h-full w-full items-center gap-3 px-2 lg:px-3">
          {BG_PHOTOS.map((p, i) => (
            <div key={i} className="flex w-1/4 justify-center">
              <div
                className="relative w-full overflow-hidden "
                style={{ height: p.height }}
              >
                <img
                  src={p.src}
                  alt=""
                  draggable={false}
                  className="absolute inset-0 h-full rounded-xl w-full object-cover shadow-[0_10px_36px_-6px_rgba(0,0,0,0.18),0_3px_10px_-2px_rgba(0,0,0,0.08)]"
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Mobile background */}
      <div className="absolute inset-0 md:hidden bg-gradient-to-br from-[#fffbe6] via-white to-[#fff5b8]" />

      {/* Login/Register card */}
      <div className="relative z-10 flex min-h-screen items-center justify-center p-4 md:p-6">
        <div className="w-full max-w-[700px] rounded-[16px] bg-white px-5 py-6 shadow-[0_4px_21.5px_rgba(0,0,0,0.16)] md:px-8 md:py-8 lg:w-[48%] animate-fadeScale">
          <div className="mb-5 flex items-center md:mb-6">
            <img
              src="/images/login/logo-full.png"
              alt="Zarah AI"
              className="h-[68px] w-auto select-none md:h-[80px]"
              draggable={false}
            />
          </div>

          {tab === "login" ? (
            <>
              <h1 className="text-[24px] font-bold leading-tight tracking-[0.18px] text-[#444342] md:text-[28px]">
                Log in to your account
              </h1>

              {error && (
                <div className="mt-5 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {error}
                </div>
              )}

              <form
                onSubmit={handleLogin}
                className="mt-4 flex flex-col gap-2 md:mt-5 md:flex-row md:items-stretch md:gap-2.5"
              >
                <input
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Brooklyn Simson"
                  required
                  className={`${inputCls} md:flex-1`}
                />

                <div className="relative md:flex-1">
                  <input
                    type={showPwd ? "text" : "password"}
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="***************"
                    required
                    className={`${inputCls} w-full pr-10`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPwd((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#444342] transition hover:text-[#1f1f1f]"
                    tabIndex={-1}
                    aria-label={showPwd ? "Hide password" : "Show password"}
                  >
                    {showPwd ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>

                <button
                  type="submit"
                  disabled={loading || !username.trim() || !password}
                  className="h-12 rounded-[8px] border-[1.5px] border-[#fbec5d] bg-[#fbec5d] px-5 text-[15px] font-semibold tracking-[0.14px] text-[#444342] shadow-[1px_1px_2px_rgba(0,0,0,0.1)] transition hover:brightness-95 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 md:w-[100px]"
                >
                  {loading ? "…" : "Login"}
                </button>
              </form>

              <div className="mt-5 flex items-center gap-3">
                <div className="h-px flex-1 bg-[#444342]/30" />
                <span className="text-[14px] tracking-[0.12px] text-[#444342]">
                  OR
                </span>
                <div className="h-px flex-1 bg-[#444342]/30" />
              </div>

              <button
                type="button"
                onClick={() => setError("Google sign-in is not yet wired up.")}
                className="mt-4 flex h-12 w-full items-center justify-center gap-2.5 rounded-[8px] border-[1.5px] border-[#444342] bg-[#2a2929] text-[15px] text-white transition hover:bg-[#1f1f1f] active:scale-[0.99]"
              >
                <GoogleIcon />
                <span>
                  Login with <span className="font-bold">Google</span>
                </span>
              </button>

              <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
                <span className="text-[14px] font-medium tracking-[0.12px] text-[#444342]">
                  Do not have an account?
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setTab("register");
                    setError(null);
                  }}
                  className="h-7 rounded-[14px] bg-[#fff690] px-3.5 text-[14px] font-medium tracking-[0.12px] text-[#1f1f1f] transition hover:bg-[#fbec5d]"
                >
                  Register
                </button>
              </div>
            </>
          ) : (
            <>
              <h1 className="text-[24px] font-bold leading-tight tracking-[0.18px] text-[#444342] md:text-[28px]">
                Create your account
              </h1>

              <p className="mt-1.5 text-[12px] leading-snug tracking-[0.12px] text-[#444342] md:text-[12.5px]">
                Join Zarah and craft smarter travel experiences for your clients.
              </p>

              {error && (
                <div className="mt-5 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {error}
                </div>
              )}

              <form
                onSubmit={handleRegister}
                className="mt-4 grid grid-cols-1 gap-2 md:mt-5 md:grid-cols-2 md:gap-2.5"
              >
                <input
                  type="text"
                  value={regFullName}
                  onChange={(e) => setRegFullName(e.target.value)}
                  placeholder="Brooklyn Simson"
                  className={inputCls}
                />
                <input
                  type="text"
                  autoComplete="username"
                  value={regUsername}
                  onChange={(e) => setRegUsername(e.target.value)}
                  placeholder="Username"
                  required
                  className={inputCls}
                />
                <input
                  type="email"
                  autoComplete="email"
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  placeholder="you@company.com"
                  required
                  className={inputCls}
                />
                <div className="relative">
                  <input
                    type={showPwd ? "text" : "password"}
                    autoComplete="new-password"
                    value={regPassword}
                    onChange={(e) => setRegPassword(e.target.value)}
                    placeholder="Password"
                    required
                    className={`${inputCls} w-full pr-10`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPwd((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#444342] transition hover:text-[#1f1f1f]"
                    tabIndex={-1}
                    aria-label={showPwd ? "Hide password" : "Show password"}
                  >
                    {showPwd ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>

                <button
                  type="submit"
                  disabled={
                    loading ||
                    !regUsername.trim() ||
                    !regEmail.trim() ||
                    !regPassword
                  }
                  className="h-12 rounded-[8px] border-[1.5px] border-[#fbec5d] bg-[#fbec5d] text-[15px] font-semibold tracking-[0.14px] text-[#444342] shadow-[1px_1px_2px_rgba(0,0,0,0.1)] transition hover:brightness-95 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 md:col-span-2"
                >
                  {loading ? "Creating…" : "Create Account"}
                </button>
              </form>

              <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
                <span className="text-[14px] font-medium tracking-[0.12px] text-[#444342]">
                  Already have an account?
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setTab("login");
                    setError(null);
                  }}
                  className="h-7 rounded-[14px] bg-[#fff690] px-3.5 text-[14px] font-medium tracking-[0.12px] text-[#1f1f1f] transition hover:bg-[#fbec5d]"
                >
                  Sign in
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Login;