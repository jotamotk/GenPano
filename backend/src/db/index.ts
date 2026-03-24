// In-memory store (no native compilation required — suitable for local dev/demo)

export interface UserRow {
  id: number
  email: string
  password: string | null
  name: string | null
  company: string | null
  role: string
  provider: string
  google_id: string | null
  verified: number
  created_at: string
  updated_at: string
}

export interface ResetTokenRow {
  id: number
  user_id: number
  token: string
  expires_at: string
  used: number
  created_at: string
}

export interface VerificationTokenRow {
  id: number
  user_id: number
  token: string
  expires_at: string
  created_at: string
}

let userIdSeq = 1
let tokenIdSeq = 1

export const users = new Map<number, UserRow>()
export const usersByEmail = new Map<string, UserRow>()
export const resetTokens = new Map<string, ResetTokenRow>()
export const verificationTokens = new Map<string, VerificationTokenRow>()

function now() {
  return new Date().toISOString()
}

export const db = {
  createUser(data: Omit<UserRow, 'id' | 'created_at' | 'updated_at'>): UserRow {
    const user: UserRow = { ...data, id: userIdSeq++, created_at: now(), updated_at: now() }
    users.set(user.id, user)
    usersByEmail.set(user.email.toLowerCase(), user)
    return user
  },

  getUserByEmail(email: string): UserRow | undefined {
    return usersByEmail.get(email.toLowerCase())
  },

  getUserById(id: number): UserRow | undefined {
    return users.get(id)
  },

  updateUser(id: number, data: Partial<UserRow>): void {
    const user = users.get(id)
    if (!user) return
    const updated = { ...user, ...data, updated_at: now() }
    users.set(id, updated)
    usersByEmail.set(updated.email.toLowerCase(), updated)
  },

  createResetToken(user_id: number, token: string, expires_at: string): void {
    const row: ResetTokenRow = { id: tokenIdSeq++, user_id, token, expires_at, used: 0, created_at: now() }
    resetTokens.set(token, row)
  },

  getResetToken(token: string): ResetTokenRow | undefined {
    return resetTokens.get(token)
  },

  markResetTokenUsed(token: string): void {
    const row = resetTokens.get(token)
    if (row) resetTokens.set(token, { ...row, used: 1 })
  },

  createVerificationToken(user_id: number, token: string, expires_at: string): void {
    const row: VerificationTokenRow = { id: tokenIdSeq++, user_id, token, expires_at, created_at: now() }
    verificationTokens.set(token, row)
  },

  getVerificationToken(token: string): VerificationTokenRow | undefined {
    return verificationTokens.get(token)
  },
}

export default db
