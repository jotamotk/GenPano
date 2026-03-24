export const zh = {
  // Common
  or: '或',
  language: '语言',

  // Login Page
  login: {
    title: '登录',
    noAccount: '没有账号？',
    signUp: '注册',
    emailLabel: '工作邮箱',
    emailPlaceholder: '你的工作邮箱，例如：Email@company.com',
    continueButton: '继续',
    forgotPassword: '忘记密码？',
    googleButton: '使用 Google 账号继续',
    googleButtonStep2: '使用 Google 账号登录',
    unregisteredHint: '该邮箱未注册，点击去注册 →',
    emailNotRegistered: '该邮箱未注册',
    loginSuccess: '登录成功',
    loginFailed: '登录失败，请检查邮箱和密码',
    passwordLabel: '密码',
    passwordPlaceholder: '输入你的密码',
    passwordEmpty: '密码为空：请输入密码',
    invalidCredentials: '用户名或密码不正确',
    editEmail: '修改邮箱',
    noAccountHint: '如果点击继续，如果账号未注册则会跳转注册',
  },

  // Register Page
  register: {
    title: '创建免费账户',
    hasAccount: '已经有账户了？',
    login: '登录',
    emailLabel: '工作邮箱',
    emailPlaceholder: '你的工作邮箱，例如：Email@company.com',
    registerButton: '注册',
    googleButton: '使用 Google 继续',
    privacyText: '注册表示我同意 GenPano 隐私政策和条款',
    privacyLink: '隐私政策和条款',
    emailExists: '该邮箱已注册，请直接登录',
    registerSuccess: '注册成功！验证邮件已发送，请查收',
  },

  // Email Sent Page
  emailSent: {
    verifyTitle: '邮件发送成功！',
    verifySubtitle: '我们已将验证邮件发送到您的邮箱，请查收并完成验证',
    resetTitle: '邮件已成功发送！',
    resetSubtitle: '我们已将密码重置邮件发送到您的邮箱',
    sentTo: 'Sent to',
    sentToZh: '已发送至',
    step1Verify: '登录你的邮箱查看验证邮件',
    step2Verify: '点击邮件中的验证按钮或链接',
    step1Reset: '登录您的电子邮件以查看密码重置邮件',
    step2Reset: '单击重置按钮以更新您的密码',
    resendButton: '重新发送邮件',
    noEmailHint: '没有收到邮件？请检查你的垃圾邮件文件夹',
    viewEmail: '查看邮件',
    nextSteps: '接下来你需要：',
    nextStepsReset: '接下来，您需要：',
  },

  // Account Setup Page
  setup: {
    title: '设置您的帐户',
    emailLabel: '公司邮箱',
    passwordLabel: '密码',
    nameLabel: '全名',
    companyLabel: '公司名称',
    namePlaceholder: '你的全名',
    companyPlaceholder: '例如：耐克',
    newsletter: '订阅我们的新闻邮件',
    submitButton: '注册',
    emailError: '请输入您的公司邮箱',
    emailInvalid: '请输入有效的公司邮箱',
    passwordError: '请输入有效密码',
    nameError: '请输入你的全名',
    companyError: '请输入你的公司名称',
    passwordInfo: '密码至少8位',
  },

  // Forgot Password
  forgotPassword: {
    title: '忘记密码？',
    noAccount: '没有账号？',
    signUp: '注册',
    description: '输入您的注册邮箱，我们将发送密码重置链接',
    emailLabel: '将重置密码链接发送至：',
    emailPlaceholder: '请输入您的公司邮箱',
    submitButton: '发送',
    backToLogin: '返回登录',
    success: '重置链接已发送，请查收邮件',
    emailNotFound: '该邮箱未注册',
    emailError: '请输入有效的公司邮箱',
  },

  // Reset Password
  resetPassword: {
    title: '重置密码',
    newPasswordLabel: '新密码',
    confirmPasswordLabel: '确认密码',
    passwordPlaceholder: '输入你的密码',
    passwordError: '请输入有效密码',
    confirmError: '请输入有效密码',
    mismatchError: '密码不匹配，请重试。',
    submitButton: 'Reset',
    passwordInfo: '密码至少8位',
  },

  // Reset Password Success
  resetSuccess: {
    title: '密码重置成功',
    description: '您的密码已成功重置。您现在可以使用新密码登录。',
    backButton: '返回',
  },

  // Validation
  validation: {
    emailRequired: '请输入邮箱地址',
    emailInvalid: '请输入有效的邮箱地址',
    emailPersonal: '请输入有效的公司邮箱',
    emailFormat: '邮箱格式不正确',
  },

  // Errors
  errors: {
    networkError: '网络异常，请稍后重试',
    serverError: '服务器异常，请联系支持',
    unknown: '未知错误，请重试',
  },
}

export type Translations = typeof zh
