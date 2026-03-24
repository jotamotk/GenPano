import type { Translations } from './zh'

export const en: Translations = {
  // Common
  or: 'Or',
  language: 'Language',

  // Login Page
  login: {
    title: 'Login',
    noAccount: 'No account?',
    signUp: 'Sign Up',
    emailLabel: 'Work Email',
    emailPlaceholder: 'Your work email, e.g. Email@company.com',
    continueButton: 'Continue',
    forgotPassword: 'Forgot password?',
    googleButton: 'Continue with Google',
    googleButtonStep2: 'Sign in with Google',
    unregisteredHint: 'Email not registered, click to sign up →',
    emailNotRegistered: 'Email not registered',
    loginSuccess: 'Login successful',
    loginFailed: 'Login failed. Please check your credentials',
    passwordLabel: 'Password',
    passwordPlaceholder: 'Enter your password',
    passwordEmpty: 'Password is empty: please enter your password',
    invalidCredentials: 'Username or password is incorrect',
    editEmail: 'Edit email',
    noAccountHint: 'If you click continue and the account is not registered, you will be redirected to register',
  },

  // Register Page
  register: {
    title: 'Create Free Account',
    hasAccount: 'Already have an account?',
    login: 'Login',
    emailLabel: 'Work Email',
    emailPlaceholder: 'Your work email, e.g. Email@company.com',
    registerButton: 'Register',
    googleButton: 'Continue with Google',
    privacyText: 'By registering, I agree to GenPano\'s Privacy Policy and Terms',
    privacyLink: 'Privacy Policy and Terms',
    emailExists: 'Email already registered. Please login instead',
    registerSuccess: 'Registration successful! Verification email sent.',
  },

  // Email Sent Page
  emailSent: {
    verifyTitle: 'Email Sent Successfully!',
    verifySubtitle: 'We have sent a verification email to your inbox. Please check and complete verification.',
    resetTitle: 'Email Sent Successfully!',
    resetSubtitle: 'We have sent a password reset email to your inbox.',
    sentTo: 'Sent to',
    sentToZh: 'Sent to',
    step1Verify: 'Log in to your email to view the verification email',
    step2Verify: 'Click the verification button or link in the email',
    step1Reset: 'Log in to your email to view the password reset email',
    step2Reset: 'Click the reset button to update your password',
    resendButton: 'Resend Email',
    noEmailHint: 'Didn\'t receive the email? Check your spam folder',
    viewEmail: 'View Email',
    nextSteps: 'Next steps:',
    nextStepsReset: 'Next, you need to:',
  },

  // Account Setup Page
  setup: {
    title: 'Set Up Your Account',
    emailLabel: 'Work Email',
    passwordLabel: 'Password',
    nameLabel: 'Full Name',
    companyLabel: 'Company Name',
    namePlaceholder: 'Your full name',
    companyPlaceholder: 'e.g. Nike',
    newsletter: 'Subscribe to our newsletter',
    submitButton: 'Register',
    emailError: 'Please enter your work email',
    emailInvalid: 'Please enter a valid work email',
    passwordError: 'Please enter a valid password',
    nameError: 'Please enter your full name',
    companyError: 'Please enter your company name',
    passwordInfo: 'Password must be at least 8 characters',
  },

  // Forgot Password
  forgotPassword: {
    title: 'Forgot Password?',
    noAccount: 'No account?',
    signUp: 'Sign Up',
    description: 'Enter your registered email and we\'ll send a reset link',
    emailLabel: 'Send reset password link to:',
    emailPlaceholder: 'Please enter your work email',
    submitButton: 'Send',
    backToLogin: 'Back to Login',
    success: 'Reset link sent. Please check your email',
    emailNotFound: 'Email not registered',
    emailError: 'Please enter a valid work email',
  },

  // Reset Password
  resetPassword: {
    title: 'Reset Password',
    newPasswordLabel: 'New Password',
    confirmPasswordLabel: 'Confirm Password',
    passwordPlaceholder: 'Enter your password',
    passwordError: 'Please enter a valid password',
    confirmError: 'Please enter a valid password',
    mismatchError: 'Passwords do not match, please try again.',
    submitButton: 'Reset',
    passwordInfo: 'Password must be at least 8 characters',
  },

  // Reset Password Success
  resetSuccess: {
    title: 'Password Reset Successful',
    description: 'Your password has been successfully reset. You can now log in with your new password.',
    backButton: 'Back',
  },

  // Validation
  validation: {
    emailRequired: 'Please enter your email',
    emailInvalid: 'Please enter a valid email address',
    emailPersonal: 'Please enter a valid work email',
    emailFormat: 'Invalid email format',
  },

  // Errors
  errors: {
    networkError: 'Network error, please try again',
    serverError: 'Server error, please contact support',
    unknown: 'Unknown error, please try again',
  },
}
