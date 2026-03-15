"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { motion } from "framer-motion";
import { Loader2, Mail, Lock, ArrowRight } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const router = useRouter();
  const { signIn, signUp } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSignUp, setIsSignUp] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isSignUp) {
        if (password.length < 6) {
          setError("Password must be at least 6 characters");
          setLoading(false);
          return;
        }
        await signUp(email, password);
      } else {
        await signIn(email, password);
      }
      router.push("/");
    } catch (err: unknown) {
      const code = (err as { code?: string })?.code ?? "";
      switch (code) {
        case "auth/user-not-found":
        case "auth/invalid-credential":
          setError("Invalid email or password");
          break;
        case "auth/email-already-in-use":
          setError("An account with this email already exists");
          break;
        case "auth/weak-password":
          setError("Password must be at least 6 characters");
          break;
        case "auth/invalid-email":
          setError("Please enter a valid email address");
          break;
        case "auth/too-many-requests":
          setError("Too many attempts. Please try again later.");
          break;
        default:
          setError("Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative z-10 flex min-h-screen flex-col items-center justify-center p-8">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="flex w-full max-w-sm flex-col items-center gap-8"
      >
        {/* Logo & Title */}
        <div className="flex flex-col items-center gap-4 text-center">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.1, duration: 0.5 }}
            className="flex h-16 w-16 items-center justify-center"
          >
            <Image
              src="/logo.svg"
              alt="Bundle Analyzer logo"
              width={64}
              height={64}
              priority
              className="h-16 w-16 object-contain"
            />
          </motion.div>
          <div>
            <h1
              className="text-2xl font-bold tracking-tight"
              style={{ color: "var(--foreground-bright)" }}
            >
              {isSignUp ? "Create Account" : "Welcome Back"}
            </h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              {isSignUp
                ? "Sign up to start analyzing bundles"
                : "Sign in to Bundle Analyzer"}
            </p>
          </div>
        </div>

        {/* Form */}
        <motion.form
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          onSubmit={handleSubmit}
          className="flex w-full flex-col gap-4"
        >
          {/* Email */}
          <div className="relative">
            <Mail
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 z-10 -translate-y-1/2"
              style={{ color: "var(--foreground)", opacity: 0.5 }}
            />
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email address"
              required
              autoComplete="email"
              className="input-modern w-full py-2.5 pl-10 pr-3"
            />
          </div>

          {/* Password */}
          <div className="relative">
            <Lock
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 z-10 -translate-y-1/2"
              style={{ color: "var(--foreground)", opacity: 0.5 }}
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              required
              autoComplete={isSignUp ? "new-password" : "current-password"}
              minLength={6}
              className="input-modern w-full py-2.5 pl-10 pr-3"
            />
          </div>

          {/* Error */}
          {error && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-sm"
              style={{ color: "var(--critical)" }}
            >
              {error}
            </motion.p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="btn-primary flex w-full items-center justify-center gap-2"
          >
            {loading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <>
                {isSignUp ? "Create Account" : "Sign In"}
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </motion.form>

        {/* Toggle */}
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          {isSignUp ? "Already have an account?" : "Don't have an account?"}{" "}
          <button
            onClick={() => {
              setIsSignUp(!isSignUp);
              setError(null);
            }}
            className="font-medium underline-offset-2 hover:underline"
            style={{ color: "var(--accent-light)" }}
          >
            {isSignUp ? "Sign in" : "Sign up"}
          </button>
        </p>
      </motion.div>
    </div>
  );
}
