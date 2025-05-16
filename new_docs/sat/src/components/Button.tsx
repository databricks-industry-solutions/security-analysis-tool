import React, { CSSProperties } from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';

type Button = {
    size?: 'sm' | 'lg' | 'small' | 'medium' | 'large' | null;
    outline?: boolean;
    variant: 'primary' | 'secondary' | 'danger' | 'warning' | 'success' | 'info' | 'link' | string;
    block?: boolean;
    disabled?: boolean;
    className?: string;
    style?: CSSProperties;
    link: string;
    label: string;
    linkClassName?: string;
}

export default function Button({
    size = null,
    outline = false,
    variant = 'primary',
    block = false,
    disabled = false,
    className,
    style,
    link,
    label,
    linkClassName,
}: Button) {
    const sizeMap = {
        sm: 'sm',
        small: 'sm',
        lg: 'lg',
        large: 'lg',
        medium: null,
    };
    const buttonSize = size ? sizeMap[size] : '';
    const sizeClass = buttonSize ? `button--${buttonSize}` : '';
    const outlineClass = outline ? 'button--outline' : '';
    const variantClass = variant ? `button--${variant}` : '';
    const blockClass = block ? 'button--block' : '';
    const disabledClass = disabled ? 'disabled' : '';
    const destination = disabled ? null : link;
    return (
        <Link to={destination} className={linkClassName}>
            <button
                className={clsx(
                    'btn',
                    'button',
                    sizeClass,
                    outlineClass,
                    variantClass,
                    blockClass,
                    disabledClass,
                    'btn-hover-black', // <-- Add this line
                    className
                )}
                style={style}
                role='button'
                aria-disabled={disabled}
            >
                {label}
            </button>
        </Link>
    );
}
