import type { FormEvent } from "react"
import { useState } from "react"

import { apiClient } from "../../services/apiClient"

function SignupPage() {
  const [companyName, setCompanyName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [success, setSuccess] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSuccess(null)
    setIsSubmitting(true)

    try {
      await apiClient.post("/auth/signup", {
        company_name: companyName,
        email,
        password,
      })
      setSuccess("Successfully signed up")
    } catch {
      setError("Could not sign up")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="max-w-md mx-auto p-6">
      <h1 className="text-2xl font-bold mb-4">Sign up</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="signup-company" className="block mb-1">
            Company name
          </label>
          <input
            id="signup-company"
            value={companyName}
            onChange={(event) => setCompanyName(event.target.value)}
            className="w-full border rounded p-2"
            required
          />
        </div>
        <div>
          <label htmlFor="signup-email" className="block mb-1">
            Email
          </label>
          <input
            id="signup-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="w-full border rounded p-2"
            required
          />
        </div>
        <div>
          <label htmlFor="signup-password" className="block mb-1">
            Password
          </label>
          <input
            id="signup-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full border rounded p-2"
            required
          />
        </div>
        <button
          type="submit"
          disabled={isSubmitting}
          className="px-4 py-2 border rounded"
        >
          {isSubmitting ? "Signing up..." : "Sign Up"}
        </button>
      </form>
      {success ? <p className="mt-3 text-green-500">{success}</p> : null}
      {error ? <p className="mt-3 text-red-500">{error}</p> : null}
    </section>
  )
}

export default SignupPage
