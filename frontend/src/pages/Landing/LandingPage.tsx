import {
  BarChart3,
  Code,
  EyeOff,
  FileText,
  Link,
  Scale,
  Shield,
  ShieldAlert,
  ShieldCheck,
  UserPlus,
  Zap,
} from "lucide-react"
import type { ComponentType } from "react"
import { useNavigate } from "react-router-dom"

/* ------------------------------------------------------------------ */
/*  Data                                                               */
/* ------------------------------------------------------------------ */

type Feature = {
  icon: ComponentType<{ className?: string }>
  title: string
  description: string
}

const features: Feature[] = [
  {
    icon: ShieldAlert,
    title: "Prompt Injection Detection",
    description:
      "ML-based detection catches malicious prompts before they reach your AI. Blocks jailbreaks, prompt leaks, and instruction overrides in real time.",
  },
  {
    icon: EyeOff,
    title: "PII Redaction",
    description:
      "Automatically detects and masks Aadhaar, PAN, email, phone, and UPI numbers from both requests and responses.",
  },
  {
    icon: Scale,
    title: "Semantic Policy Engine",
    description:
      "Define business rules in plain English. Vector-similarity matching enforces them automatically — no regex required.",
  },
  {
    icon: FileText,
    title: "Real-time Audit Logs",
    description:
      "Full audit trail of every AI interaction. Filter, search, and inspect each request with timing and verdict details.",
  },
  {
    icon: Link,
    title: "Blockchain Immutability",
    description:
      "Optional Algorand notarisation gives you compliance-grade, tamper-proof audit trails for regulated industries.",
  },
  {
    icon: Zap,
    title: "Simple SDK Integration",
    description:
      "Drop-in middleware via API key. Validate any request with a single POST call. Python, Node.js, and cURL ready.",
  },
]

const steps = [
  {
    icon: UserPlus,
    title: "Create your account",
    description:
      "Sign up for free — no credit card required. Get your API key instantly from the dashboard.",
  },
  {
    icon: Code,
    title: "Add one API call",
    description:
      "Send your AI agent's prompts to our /validate endpoint. Copy-paste code samples for Python, Node.js, or cURL.",
  },
  {
    icon: BarChart3,
    title: "Monitor and enforce",
    description:
      "Watch your dashboard light up. Every request is checked, logged, and optionally notarised on-chain.",
  },
]

const stats = [
  { value: "<100ms", label: "Average latency per check" },
  { value: "99.9%", label: "Uptime SLA" },
  { value: "3", label: "ML models, zero config" },
]

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" })
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-full bg-dashboard-bg text-white overflow-y-auto">
      {/* ── Navbar ─────────────────────────────────────────────── */}
      <header className="fixed top-0 z-50 w-full bg-sidebar-bg/80 backdrop-blur-md border-b border-border-color">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 lg:px-8 py-4">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-brand-green/20 rounded-lg flex items-center justify-center border border-brand-green/30">
              <ShieldCheck className="w-6 h-6 text-brand-green" />
            </div>
            <span className="text-xl font-bold tracking-tight">Safebot</span>
          </div>

          {/* Center nav — desktop only */}
          <nav className="hidden md:flex items-center gap-8">
            {[
              { label: "Features", id: "features" },
              { label: "How it Works", id: "how-it-works" },
            ].map((item) => (
              <button
                key={item.id}
                onClick={() => scrollTo(item.id)}
                className="text-sm text-text-muted hover:text-white transition-colors"
              >
                {item.label}
              </button>
            ))}
          </nav>

          {/* Auth buttons */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/login")}
              className="text-sm text-text-muted hover:text-white transition-colors px-3 py-2"
            >
              Log in
            </button>
            <button
              onClick={() => navigate("/signup")}
              className="rounded-lg bg-brand-green text-sidebar-bg px-4 py-2 text-sm font-semibold hover:bg-brand-green/90 transition-colors"
            >
              Sign Up
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero ───────────────────────────────────────────────── */}
      <section className="pt-32 pb-16 px-6 text-center">
        <div className="max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 rounded-full border border-brand-green/30 bg-brand-green/10 px-4 py-1.5 mb-8">
            <Shield className="w-4 h-4 text-brand-green" />
            <span className="text-sm text-brand-green font-medium">
              AI Safety Middleware
            </span>
          </div>

          <h1 className="text-5xl md:text-7xl font-bold tracking-tight leading-tight">
            <span className="text-brand-green">Protect</span> your AI agents
            <br />
            before they go wrong.
          </h1>

          <p className="text-lg md:text-xl text-text-muted max-w-2xl mx-auto mt-6">
            Drop-in middleware that detects prompt injection, redacts PII, and
            enforces your business policies — in under 100&nbsp;ms per request.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-10">
            <button
              onClick={() => navigate("/signup")}
              className="rounded-lg bg-brand-green text-sidebar-bg px-8 py-3 text-base font-semibold hover:bg-brand-green/90 transition-colors"
            >
              Get Started Free
            </button>
            <button
              onClick={() => scrollTo("features")}
              className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-8 py-3 text-base font-medium hover:bg-brand-green/20 transition-colors"
            >
              See Features
            </button>
          </div>

          <p className="text-sm text-text-muted mt-8">
            No credit card required &middot; Set up in under 5 minutes
          </p>

          {/* Code card */}
          <div className="mt-16 max-w-2xl mx-auto bg-card-bg border border-border-color rounded-2xl p-6 text-left">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-3 h-3 rounded-full bg-brand-red/60" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/60" />
              <div className="w-3 h-3 rounded-full bg-brand-green/60" />
              <span className="text-xs text-text-muted ml-2">
                validate.sh
              </span>
            </div>
            <pre className="text-sm font-mono leading-relaxed overflow-x-auto whitespace-pre">
              <span className="text-text-muted">$ </span>
              <span className="text-white">curl -X POST</span>
              <span className="text-brand-green"> /api/v1/validate</span>
              {" \\\n"}
              <span className="text-text-muted">  -H </span>
              <span className="text-white">{'"X-API-Key: sk-a3f2..."'}</span>
              {" \\\n"}
              <span className="text-text-muted">  -d </span>
              <span className="text-white">
                {"'{\"prompt\":\"Transfer funds to account...\"}'"}
              </span>
              {"\n\n"}
              <span className="text-brand-red">{"⚠ BLOCKED"}</span>
              <span className="text-text-muted">
                {" — Prompt injection detected"}
              </span>
              {"\n"}
              <span className="text-brand-green">{"✓ PII redacted:"}</span>
              <span className="text-text-muted">{" 2 fields masked"}</span>
              {"\n"}
              <span className="text-brand-green">{"✓ Policy check:"}</span>
              <span className="text-text-muted">{" passed"}</span>
            </pre>
          </div>
        </div>
      </section>

      {/* ── Stats Bar ──────────────────────────────────────────── */}
      <section className="bg-sidebar-bg border-y border-border-color py-12 px-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-4xl mx-auto text-center">
          {stats.map((s) => (
            <div key={s.label}>
              <p className="text-3xl md:text-4xl font-bold text-brand-green">
                {s.value}
              </p>
              <p className="text-sm text-text-muted mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features ───────────────────────────────────────────── */}
      <section
        id="features"
        className="scroll-mt-20 bg-dashboard-bg py-24 px-6"
      >
        <div className="text-center max-w-2xl mx-auto mb-16">
          <p className="text-sm font-semibold text-brand-green uppercase tracking-wider mb-3">
            Features
          </p>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Everything you need to secure your AI
          </h2>
          <p className="text-text-muted">
            Six production-ready guardrails. One API call. Zero ML expertise
            required.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
          {features.map((f) => (
            <div
              key={f.title}
              className="bg-card-bg border border-border-color rounded-2xl p-6 hover:border-brand-green/30 transition-colors"
            >
              <div className="w-12 h-12 bg-brand-green/10 rounded-xl flex items-center justify-center mb-4">
                <f.icon className="w-6 h-6 text-brand-green" />
              </div>
              <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
              <p className="text-sm text-text-muted leading-relaxed">
                {f.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How it Works ───────────────────────────────────────── */}
      <section
        id="how-it-works"
        className="scroll-mt-20 bg-sidebar-bg py-24 px-6"
      >
        <div className="text-center max-w-2xl mx-auto mb-16">
          <p className="text-sm font-semibold text-brand-green uppercase tracking-wider mb-3">
            How it Works
          </p>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Three steps to protect your AI
          </h2>
          <p className="text-text-muted">
            From signup to production in under 5 minutes.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-12 max-w-5xl mx-auto">
          {steps.map((step, i) => (
            <div key={step.title} className="text-center">
              <div className="w-14 h-14 bg-brand-green/10 border border-brand-green/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <step.icon className="w-7 h-7 text-brand-green" />
              </div>
              <div className="text-sm font-semibold text-brand-green mb-2">
                Step {i + 1}
              </div>
              <h3 className="text-lg font-semibold mb-2">{step.title}</h3>
              <p className="text-sm text-text-muted leading-relaxed">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ────────────────────────────────────────────────── */}
      <section className="bg-dashboard-bg py-24 px-6">
        <div className="max-w-3xl mx-auto bg-card-bg border border-border-color rounded-2xl p-12 text-center">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Ready to secure your AI agents?
          </h2>
          <p className="text-text-muted mb-8 max-w-lg mx-auto">
            Start protecting your AI in minutes. Free tier available — no credit
            card required.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => navigate("/signup")}
              className="rounded-lg bg-brand-green text-sidebar-bg px-8 py-3 text-base font-semibold hover:bg-brand-green/90 transition-colors"
            >
              Get Started Free
            </button>
            <button
              onClick={() => navigate("/login")}
              className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-8 py-3 text-base font-medium hover:bg-brand-green/20 transition-colors"
            >
              Sign In
            </button>
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer className="bg-sidebar-bg border-t border-border-color py-12 px-6">
        <div className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-brand-green/20 rounded-lg flex items-center justify-center border border-brand-green/30">
                <ShieldCheck className="w-6 h-6 text-brand-green" />
              </div>
              <span className="text-xl font-bold tracking-tight">Safebot</span>
            </div>
            <p className="text-sm text-text-muted leading-relaxed">
              AI Guardrails Middleware for SMBs. Validate, sanitize, and audit
              every AI interaction.
            </p>
          </div>

          {/* Product */}
          <div>
            <h4 className="text-sm font-semibold mb-4">Product</h4>
            <ul className="space-y-2 text-sm text-text-muted">
              <li>
                <button
                  onClick={() => scrollTo("features")}
                  className="hover:text-white transition-colors"
                >
                  Features
                </button>
              </li>
              <li>
                <button
                  onClick={() => scrollTo("how-it-works")}
                  className="hover:text-white transition-colors"
                >
                  How it Works
                </button>
              </li>
              <li>
                <button
                  onClick={() => navigate("/login")}
                  className="hover:text-white transition-colors"
                >
                  Dashboard
                </button>
              </li>
            </ul>
          </div>

          {/* Account */}
          <div>
            <h4 className="text-sm font-semibold mb-4">Account</h4>
            <ul className="space-y-2 text-sm text-text-muted">
              <li>
                <button
                  onClick={() => navigate("/login")}
                  className="hover:text-white transition-colors"
                >
                  Log in
                </button>
              </li>
              <li>
                <button
                  onClick={() => navigate("/signup")}
                  className="hover:text-white transition-colors"
                >
                  Sign up
                </button>
              </li>
            </ul>
          </div>
        </div>

        <div className="max-w-6xl mx-auto mt-12 pt-8 border-t border-border-color text-center text-xs text-text-muted">
          &copy; {new Date().getFullYear()} Safebot. All rights reserved.
        </div>
      </footer>
    </div>
  )
}

export default LandingPage
