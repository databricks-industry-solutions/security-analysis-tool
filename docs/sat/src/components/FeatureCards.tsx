import React from 'react';

interface Feature {
  title: string;
  href: string;
  description: string;
}

interface FeatureCardsProps {
  features: Feature[];
}

export default function FeatureCards({ features }: FeatureCardsProps) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
      {features.map((feature, index) => (
        <a key={index} href={feature.href} className="feature-card">
          <h3>{feature.title}</h3>
          <p>{feature.description}</p>
        </a>
      ))}
    </div>
  );
}
