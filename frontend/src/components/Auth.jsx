import { useState } from "react";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { api } from "../api";
import { CarArt } from "../CarArt";
import { Brand, Field } from "./ui";

export default function Auth({ onSession }) {
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      onSession(
        await api("/auth/" + (register ? "register" : "login"), {
          method: "POST",
          body: data,
        }),
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <section className="auth-story">
        <Brand />
        <div>
          <p className="eyebrow light">A BETTER WAY TO DRIVE BUSINESS</p>
          <h1>
            Your next chapter.
            <br />
            On four wheels.
          </h1>
          <p>
            Discover the right vehicle. Keep your inventory moving. Everything
            in one place.
          </p>
          <div className="auth-car">
            <CarArt color="#b6c6b5" category="SUV" />
          </div>
        </div>
        <small>Good vehicles. Great possibilities.</small>
      </section>
      <section className="auth-form">
        <div className="auth-box">
          <span className="mini-label">WELCOME TO FORECOURT</span>
          <h2>{register ? "Create your account." : "Good to see you."}</h2>
          <p className="muted">
            {register
              ? "Your private workspace is created automatically with 200 synthetic Indian listings and admin access. Your changes are saved and stay private."
              : "Sign in to explore what’s in the forecourt."}
          </p>
          <form onSubmit={submit}>
            <Field
              label="Email address"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              required
              maxLength={254}
            />
            <Field
              label="Password"
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              placeholder={
                register ? "At least 10 characters" : "Enter your password"
              }
              minLength={register ? 10 : 1}
              maxLength={128}
              required
            />
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button className="primary wide" disabled={busy}>
              {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
              <ArrowRight size={18} />
            </button>
          </form>
          <p className="auth-toggle">
            {register ? "Already have an account?" : "New to Forecourt?"}{" "}
            <button
              disabled={busy}
              onClick={() => {
                setRegister(!register);
                setError("");
              }}
            >
              {register ? "Sign in" : "Create an account"}
            </button>
          </p>
          <div className="secure-note">
            <ShieldCheck size={16} /> Your inventory, securely connected.
          </div>
        </div>
      </section>
    </main>
  );
}
