import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import * as Dialog from '@radix-ui/react-dialog';
import { X, CheckCircle, Loader } from 'lucide-react';
import Button from '../ui/Button';

/* ─────────────────────────────────────────────────────────────
   LeadFormModal — PRD §4.9 (Consulting Conversion)
   ─────────────────────────────────────────────────────────────
   Modal triggered from DiagnosticsPage "联系 GEO 顾问" CTA.
   Collects: brand name (read-only), contact name, phone/email,
   concern checkboxes, then shows success state + PDF status.

   Props:
     open: boolean
     onClose: () => void
     brandName: string (auto-filled)
     onSubmit: (data) => Promise<void>
*/

/* ── i18n (placeholder) ── */
const t = {
  title: '联系 GEO 顾问',
  subtitle: '我们的顾问团队将在 24 小时内为您提供定制化的诊断报告和优化建议',
  field_brand: '品牌名称',
  field_name: '联系人姓名',
  field_namePlaceholder: '请输入您的姓名',
  field_contact: '手机或邮箱',
  field_contactPlaceholder: '输入手机号（大陆）或邮箱地址',
  field_concerns: '最关心的问题（至少选一项）',
  concern_visibility: '品牌可见度下降',
  concern_sentiment: '负面情感增长',
  concern_competitor: '竞品威胁',
  concern_other: '其他',
  btn_submit: '提交',
  btn_cancel: '取消',
  success_title: '已提交',
  success_message: '感谢您的咨询，我们将在 24 小时内联系您',
  success_pdf: '诊断报告 PDF 生成中...',
  error_nameRequired: '请输入联系人姓名',
  error_contactRequired: '请输入手机号或邮箱',
  error_contactInvalid: '请输入有效的手机号（1开头，11位）或邮箱地址',
  error_concernsRequired: '请至少选择一项关心的问题',
};

/* ── Validation schema ── */
const phoneRegex = /^1[3-9]\d{9}$/;
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const contactSchema = z.string()
  .refine(
    (val) => phoneRegex.test(val) || emailRegex.test(val),
    '请输入有效的手机号（1开头，11位）或邮箱地址'
  );

const formSchema = z.object({
  brandName: z.string().min(1),
  contactName: z.string().min(1, t.error_nameRequired),
  contact: contactSchema,
  concerns: z.array(z.string()).min(1, t.error_concernsRequired),
});

/* ── LeadFormModal ── */
export default function LeadFormModal({ open, onClose, brandName, onSubmit }) {
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm({
    resolver: zodResolver(formSchema),
    defaultValues: {
      brandName,
      contactName: '',
      contact: '',
      concerns: [],
    },
  });

  const onSubmitHandler = async (data) => {
    setIsLoading(true);
    try {
      await onSubmit(data);
      setIsSubmitted(true);
    } catch (error) {
      console.error('Form submission error:', error);
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    // Reset when closing
    setIsSubmitted(false);
    setIsLoading(false);
    reset();
    onClose();
  };

  return (
    <Dialog.Root open={open} onOpenChange={handleClose}>
      <Dialog.Portal>
        {/* Backdrop */}
        <Dialog.Overlay className="fixed inset-0 bg-black/30 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />

        {/* Modal */}
        <Dialog.Content className="fixed left-[50%] top-[50%] z-50 translate-x-[-50%] translate-y-[-50%] w-full max-w-[480px] rounded-card p-6 bg-themed-card shadow-elevated data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]">

          {/* Close button */}
          <Dialog.Close asChild>
            <button className="absolute top-4 right-4 inline-flex items-center justify-center rounded-btn p-1 text-themed-muted hover:text-themed-primary hover:bg-themed-subtle transition-colors">
              <X width={18} height={18} />
            </button>
          </Dialog.Close>

          {/* Success state */}
          {isSubmitted ? (
            <div className="flex flex-col items-center text-center space-y-4 py-6">
              <div className="flex items-center justify-center w-16 h-16 rounded-full bg-themed-accent-soft">
                <CheckCircle width={32} height={32} className="text-themed-accent" />
              </div>
              <Dialog.Title className="text-heading-2 font-brand font-bold text-themed-primary">
                {t.success_title}
              </Dialog.Title>
              <p className="text-body text-themed-muted">
                {t.success_message}
              </p>
              <div className="w-full p-4 rounded-card bg-themed-subtle border border-themed-subtle">
                <div className="flex items-center gap-2">
                  <Loader width={16} height={16} className="text-themed-accent animate-spin" />
                  <span className="text-sm text-themed-body">{t.success_pdf}</span>
                </div>
              </div>
              <Button
                variant="primary"
                size="md"
                onClick={handleClose}
                className="w-full mt-2"
              >
                关闭
              </Button>
            </div>
          ) : (
            /* Form state */
            <>
              <Dialog.Title className="text-heading-2 font-brand font-bold text-themed-primary mb-1">
                {t.title}
              </Dialog.Title>
              <Dialog.Description className="text-body text-themed-muted mb-6">
                {t.subtitle}
              </Dialog.Description>

              <form onSubmit={handleSubmit(onSubmitHandler)} className="space-y-5">
                {/* Brand name (read-only) */}
                <div>
                  <label className="block text-sm font-medium text-themed-body mb-2">
                    {t.field_brand}
                  </label>
                  <input
                    type="text"
                    readOnly
                    {...register('brandName')}
                    className="t-input bg-themed-subtle cursor-not-allowed"
                  />
                </div>

                {/* Contact name */}
                <div>
                  <label className="block text-sm font-medium text-themed-body mb-2">
                    {t.field_name}
                  </label>
                  <input
                    type="text"
                    placeholder={t.field_namePlaceholder}
                    {...register('contactName')}
                    className={`t-input ${errors.contactName ? 't-input-error' : ''}`}
                  />
                  {errors.contactName && (
                    <p className="mt-1 text-xs text-danger">{errors.contactName.message}</p>
                  )}
                </div>

                {/* Phone or email */}
                <div>
                  <label className="block text-sm font-medium text-themed-body mb-2">
                    {t.field_contact}
                  </label>
                  <input
                    type="text"
                    placeholder={t.field_contactPlaceholder}
                    {...register('contact')}
                    className={`t-input ${errors.contact ? 't-input-error' : ''}`}
                  />
                  {errors.contact && (
                    <p className="mt-1 text-xs text-danger">{errors.contact.message}</p>
                  )}
                </div>

                {/* Concerns checkboxes */}
                <div>
                  <label className="block text-sm font-medium text-themed-body mb-3">
                    {t.field_concerns}
                  </label>
                  <div className="space-y-2">
                    {[
                      { id: 'visibility', label: t.concern_visibility },
                      { id: 'sentiment', label: t.concern_sentiment },
                      { id: 'competitor', label: t.concern_competitor },
                      { id: 'other', label: t.concern_other },
                    ].map((concern) => (
                      <label key={concern.id} className="flex items-center gap-3 cursor-pointer group">
                        <input
                          type="checkbox"
                          value={concern.id}
                          {...register('concerns')}
                          className="w-4 h-4 rounded cursor-pointer"
                          style={{ accentColor: 'var(--color-accent)' }}
                        />
                        <span className="text-sm text-themed-body group-hover:text-themed-primary transition-colors">
                          {concern.label}
                        </span>
                      </label>
                    ))}
                  </div>
                  {errors.concerns && (
                    <p className="mt-2 text-xs text-danger">{errors.concerns.message}</p>
                  )}
                </div>

                {/* Buttons */}
                <div className="flex gap-3 pt-4">
                  <Button
                    variant="secondary"
                    size="md"
                    onClick={handleClose}
                    className="flex-1"
                    disabled={isLoading}
                  >
                    {t.btn_cancel}
                  </Button>
                  <Button
                    variant="primary"
                    size="md"
                    type="submit"
                    className="flex-1"
                    disabled={isLoading}
                  >
                    {isLoading ? (
                      <span className="flex items-center gap-2 justify-center">
                        <Loader width={16} height={16} className="animate-spin" />
                        提交中...
                      </span>
                    ) : (
                      t.btn_submit
                    )}
                  </Button>
                </div>
              </form>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
