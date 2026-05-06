export const zh = {
  // Common
  or: '或',
  language: '语言',

  // Login Page
  login: {
    title: '登录',
    noAccount: '没有账号？',
    signUp: '注册',
    emailLabel: '邮箱',
    emailPlaceholder: '你的邮箱，例如：name@example.com',
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
    emailLabel: '邮箱',
    emailPlaceholder: '你的邮箱，例如：name@example.com',
    registerButton: '注册',
    googleButton: '使用 Google 继续',
    privacyText: '注册表示我同意 GenPano 隐私政策和条款',
    privacyLink: '隐私政策和条款',
    emailExists: '该邮箱已注册，请直接登录',
    registerSuccess: '验证邮件已发送，请查收',
  },

  // Email Sent Page
  emailSent: {
    verifyTitle: '请查收邮箱',
    verifySubtitle: '验证邮件已发送。完成验证后，你可以继续设置账号。',
    resetTitle: '请查收邮箱',
    resetSubtitle: '如果该邮箱已注册，我们会发送密码重置邮件。',
    sentTo: 'Sent to',
    sentToZh: '已发送至',
    step1Verify: '打开邮箱，查看 GenPano 验证邮件',
    step2Verify: '点击邮件中的按钮继续设置账号',
    step1Reset: '打开邮箱，查看 GenPano 密码重置邮件',
    step2Reset: '点击邮件中的按钮设置新密码',
    resendButton: '重新发送邮件',
    noEmailHint: '没有收到邮件？请检查你的垃圾邮件文件夹',
    viewEmail: '查看邮件',
    nextSteps: '下一步',
    nextStepsReset: '下一步',
  },

  // Account Setup Page
  setup: {
    title: '完善账号信息',
    emailLabel: '邮箱',
    passwordLabel: '密码',
    nameLabel: '全名',
    companyLabel: '公司名称',
    namePlaceholder: '你的全名',
    companyPlaceholder: '例如：耐克',
    newsletter: '订阅我们的新闻邮件',
    submitButton: '完成设置',
    emailError: '请输入您的邮箱',
    emailInvalid: '请输入有效的邮箱地址',
    passwordError: '密码至少 8 位，且需包含大小写字母和数字',
    nameError: '请输入你的全名',
    companyError: '请输入你的公司名称',
    passwordInfo: '至少 8 位，包含大小写字母和数字',
  },

  // Forgot Password
  forgotPassword: {
    title: '忘记密码？',
    noAccount: '没有账号？',
    signUp: '注册',
    description: '输入您的注册邮箱，我们将发送密码重置链接',
    emailLabel: '将重置密码链接发送至：',
    emailPlaceholder: '请输入您的邮箱',
    submitButton: '发送',
    backToLogin: '返回登录',
    success: '重置链接已发送，请查收邮件',
    emailNotFound: '该邮箱未注册',
    emailError: '请输入有效的邮箱地址',
  },

  // Reset Password
  resetPassword: {
    title: '重置密码',
    newPasswordLabel: '新密码',
    confirmPasswordLabel: '确认密码',
    passwordPlaceholder: '输入你的密码',
    passwordError: '密码至少 8 位，且需包含大小写字母和数字',
    confirmError: '请输入有效密码',
    mismatchError: '密码不匹配，请重试。',
    submitButton: 'Reset',
    passwordInfo: '至少 8 位，包含大小写字母和数字',
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
    emailFormat: '邮箱格式不正确',
  },

  // Errors
  errors: {
    networkError: '网络异常，请稍后重试',
    serverError: '服务器异常，请联系支持',
    unknown: '未知错误，请重试',
    copy: '复制详情',
    copied: '已复制',
    showMore: '显示完整诊断',
    requestId: '请求 ID',
    // 错误码 → 用户文案。code 本身始终展示在错误面板顶部，便于支持检索；
    // 未翻译的 code 会回退到 problem.title。
    codes: {
      unauthorized: '登录状态已失效，请重新登录。',
      forbidden: '没有访问该资源的权限。',
      not_found: '资源不存在或已删除。',
      gone: '该资源已不可用。',
      validation_error: '输入校验未通过。',
      conflict: '当前状态与该操作冲突。',
      rate_limit_exceeded: '请求过于频繁，请稍后再试。',
      internal_error: '服务端错误，请稍后重试或联系支持。',
      service_degraded: '服务当前不可用，请稍后再试。',
      network_error: '网络异常，请检查网络后重试。',
      invalid_credentials: '邮箱或密码错误。',
      MCP_AUTH_REQUIRED: '需要 MCP API key。',
      project_name_taken: '项目名称已存在。',
      competitor_capacity_full: '竞品列表已满。',
    } as Record<string, string>,
  },
}

export type Translations = typeof zh
