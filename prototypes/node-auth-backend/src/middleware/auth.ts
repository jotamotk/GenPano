import { Request, Response, NextFunction } from 'express'
import { verifyToken } from '../utils/jwt'

export interface AuthRequest extends Request {
  userId?: number
  userEmail?: string
}

export function requireAuth(req: AuthRequest, res: Response, next: NextFunction): void {
  const authHeader = req.headers.authorization
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    res.status(401).json({ error: 'UNAUTHORIZED', message: 'Authentication required' })
    return
  }

  const token = authHeader.slice(7)
  try {
    const payload = verifyToken(token)
    req.userId = payload.userId
    req.userEmail = payload.email
    next()
  } catch {
    res.status(401).json({ error: 'INVALID_TOKEN', message: 'Invalid or expired token' })
  }
}
