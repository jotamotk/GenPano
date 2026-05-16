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
    emailLabel: 'Email',
    emailPlaceholder: 'Your email, e.g. name@example.com',
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
    emailLabel: 'Email',
    emailPlaceholder: 'Your email, e.g. name@example.com',
    registerButton: 'Register',
    googleButton: 'Continue with Google',
    privacyText: 'By registering, I agree to GenPano\'s Privacy Policy and Terms',
    privacyLink: 'Privacy Policy and Terms',
    emailExists: 'Email already registered. Please login instead',
    registerSuccess: 'Verification email sent.',
  },

  // Email Sent Page
  emailSent: {
    verifyTitle: 'Check your email',
    verifySubtitle: 'We sent a verification email. After verification, you can continue setting up your account.',
    resetTitle: 'Check your email',
    resetSubtitle: "If this email is registered, we'll send a password reset email.",
    sentTo: 'Sent to',
    sentToZh: 'Sent to',
    step1Verify: 'Open your inbox and find the GenPano verification email',
    step2Verify: 'Click the button in the email to continue setup',
    step1Reset: 'Open your inbox and find the GenPano password reset email',
    step2Reset: 'Click the button in the email to set a new password',
    resendButton: 'Resend email',
    noEmailHint: 'No email yet? Check your spam folder.',
    nextSteps: 'Next step',
    nextStepsReset: 'Next step',
  },

  // Account Setup Page
  setup: {
    title: 'Set Up Your Account',
    emailLabel: 'Email',
    passwordLabel: 'Password',
    nameLabel: 'Full Name',
    companyLabel: 'Company Name',
    namePlaceholder: 'Your full name',
    companyPlaceholder: 'e.g. Nike',
    newsletter: 'Subscribe to our newsletter',
    submitButton: 'Register',
    emailError: 'Please enter your email',
    emailInvalid: 'Please enter a valid email address',
    passwordError: 'Password must be at least 8 characters and include upper/lowercase letters and a number',
    nameError: 'Please enter your full name',
    companyError: 'Please enter your company name',
    passwordInfo: 'At least 8 characters with upper/lowercase letters and a number',
  },

  // Forgot Password
  forgotPassword: {
    title: 'Forgot Password?',
    noAccount: 'No account?',
    signUp: 'Sign Up',
    description: 'Enter your registered email and we\'ll send a reset link',
    emailLabel: 'Send reset password link to:',
    emailPlaceholder: 'Please enter your email',
    submitButton: 'Send',
    backToLogin: 'Back to Login',
    success: 'Reset link sent. Please check your email',
    emailNotFound: 'Email not registered',
    emailError: 'Please enter a valid email address',
  },

  // Reset Password
  resetPassword: {
    title: 'Reset Password',
    newPasswordLabel: 'New Password',
    confirmPasswordLabel: 'Confirm Password',
    passwordPlaceholder: 'Enter your password',
    passwordError: 'Password must be at least 8 characters and include upper/lowercase letters and a number',
    confirmError: 'Please enter a valid password',
    mismatchError: 'Passwords do not match, please try again.',
    submitButton: 'Reset',
    passwordInfo: 'At least 8 characters with upper/lowercase letters and a number',
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
    emailFormat: 'Invalid email format',
  },

  // Errors
  errors: {
    networkError: 'Network error, please try again',
    serverError: 'Server error, please contact support',
    unknown: 'Unknown error, please try again',
    copy: 'Copy details',
    copied: 'Copied',
    showMore: 'Show full details',
    requestId: 'Request ID',
    retry: 'Retry',
    retrying: 'Retrying...',
    loading: 'Loading...',
    failedToLoad: 'Failed to load',
    // Code → user-facing message. The code itself is always shown in the
    // panel header so support can search for it even when no translation
    // exists.
    codes: {
      unauthorized: 'You are signed out. Please log in again.',
      forbidden: 'You do not have access to this resource.',
      not_found: 'Resource not found.',
      gone: 'This resource is no longer available.',
      validation_error: 'Invalid input.',
      conflict: 'This action conflicts with the current state.',
      rate_limit_exceeded: 'You are sending requests too quickly. Try again shortly.',
      internal_error: 'Server error. Please try again or contact support.',
      service_degraded: 'Service is currently degraded. Please try again later.',
      bad_gateway: 'Upstream service is temporarily unavailable. Please retry.',
      gateway_timeout: 'Upstream service timed out. Please retry.',
      network_error: 'Network error. Please check your connection.',
      invalid_credentials: 'Invalid email or password.',
      MCP_AUTH_REQUIRED: 'MCP API key required.',
      project_name_taken: 'A project with this name already exists.',
      competitor_capacity_full: 'Competitor list is at capacity.',
    } as Record<string, string>,
  },
}
